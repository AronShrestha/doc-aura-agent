from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import current_user
from ..models import GithubInstallation, GithubOAuthToken, Repo, AnalysisRun, DocSection, Artifact, ArtifactEdge, GeneratedDoc, PullRequest, PrAnalysisRun, DocDiff, User
from ..schemas import AnalyzeRepoRequest, AnalyzeRepoResponse, RunResponse, SearchRequest, DocSectionResponse, GeneratedDocResponse
from ..services.github_app import (
    GithubAppError,
    build_app_jwt,
    create_installation_token,
    list_installation_repositories,
)
from ..services.github_oauth import list_user_repositories
from ..config import settings

router = APIRouter(prefix="/api/v1", tags=["analysis"])
logger = logging.getLogger(__name__)


@router.post("/repos/analyze", response_model=AnalyzeRepoResponse)
async def analyze_repo(req: AnalyzeRepoRequest, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.info("analyze repo requested", extra={"event": "analyze_repo_request"})
    repos = []
    installation_id = req.installation_id

    token_row = (await session.execute(select(GithubOAuthToken).where(GithubOAuthToken.user_id == user.id))).scalar_one_or_none()
    if token_row:
        try:
            repos = await list_user_repositories(token_row.access_token)
        except Exception:
            repos = []

    if not repos and installation_id:
        inst = (await session.execute(
            select(GithubInstallation).where(
                GithubInstallation.user_id == user.id,
                GithubInstallation.installation_id == installation_id,
            )
        )).scalar_one_or_none()
        if not inst:
            raise HTTPException(status_code=403, detail="installation_not_owned")
        try:
            app_jwt = build_app_jwt(settings.github_app_id, settings.github_app_private_key)
            installation_token = await create_installation_token(app_jwt, installation_id)
            repos = await list_installation_repositories(installation_token)
        except GithubAppError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="github_app_upstream_error") from exc

    if not repos:
        logger.warning("analyze repo failed; no repositories available", extra={"event": "analyze_repo_no_repos"})
        raise HTTPException(status_code=400, detail="no_repositories_available")
    repo_data = next((r for r in repos if r["id"] == req.github_repo_id), None)
    if not repo_data:
        logger.warning("analyze repo failed; invalid repo", extra={"event": "analyze_repo_invalid_repo"})
        raise HTTPException(status_code=400, detail="invalid_repo_for_installation")

    repo = (await session.execute(
        select(Repo).where(
            Repo.user_id == user.id,
            Repo.github_repo_id == req.github_repo_id,
        )
    )).scalar_one_or_none()
    if not repo:
        repo = Repo(
            user_id=user.id,
            github_repo_id=req.github_repo_id,
            full_name=repo_data["full_name"],
            default_branch=repo_data["default_branch"],
            installation_id=installation_id or "oauth",
            owner=repo_data["owner"],
            name=repo_data["name"],
        )
        session.add(repo)
        await session.flush()

    run = AnalysisRun(
        repo_id=repo.id,
        user_id=user.id,
        status="queued",
        stage="queued",
        progress=0,
        branch=req.branch or repo.default_branch,
        commit_sha=req.commit_sha or "",
    )
    session.add(run)
    await session.commit()

    run_id = run.id

    from ..main import app_state
    await app_state.queue.start()
    await app_state.queue.enqueue(run.id)
    logger.info("analysis queued", extra={"run_id": run.id, "repo_id": repo.id, "event": "analysis_queued"})

    return AnalyzeRepoResponse(run_id=run.id, repo_id=repo.id, status="queued")


@router.get("/runs/{run_id}", response_model=RunResponse)
async def run_status(run_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("run status requested", extra={"run_id": run_id, "event": "run_status"})
    run = (await session.execute(
        select(AnalysisRun).where(AnalysisRun.id == run_id, AnalysisRun.user_id == user.id)
    )).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    repo = (await session.execute(select(Repo).where(Repo.id == run.repo_id))).scalar_one_or_none()
    activity_tail = (run.activity or [])[-60:] if run.activity else []
    return RunResponse(
        run_id=run.id,
        repo_id=run.repo_id,
        repo_full_name=repo.full_name if repo else None,
        status=run.status,
        stage=run.stage,
        progress=run.progress,
        error=run.error,
        quality_report=run.quality_report,
        activity=activity_tail,
    )


@router.get("/repos/{repo_id}/docs/index")
async def docs_index(repo_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("docs index requested", extra={"repo_id": repo_id, "event": "docs_index"})
    run = await _latest_run(session, repo_id, user)
    docs = (await session.execute(select(GeneratedDoc).where(GeneratedDoc.run_id == run.id).order_by(GeneratedDoc.slug_path))).scalars().all()
    manifest = (run.quality_report or {}).get("manifest") or {}
    return {
        "repo_id": repo_id,
        "run_id": run.id,
        "codebase_profile": manifest.get("codebase_profile") or {},
        "manifest_tree": manifest.get("tree") or [],
        "sections": [
            {
                "section_id": d.artifact_id,
                "title": d.title,
                "diataxis_type": _diataxis_for_category(d.category),
                "slug_path": d.slug_path,
            }
            for d in docs
        ],
    }


@router.get("/repos/{repo_id}/docs/{section_id}", response_model=DocSectionResponse)
async def docs_get(repo_id: int, section_id: str, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("doc requested", extra={"repo_id": repo_id, "event": "docs_get"})
    run = await _latest_run(session, repo_id, user)
    doc = (await session.execute(select(GeneratedDoc).where(GeneratedDoc.run_id == run.id, GeneratedDoc.artifact_id == section_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="section_not_found")
    return {
        "section_id": doc.artifact_id,
        "title": doc.title,
        "diataxis_type": _diataxis_for_category(doc.category),
        "content_md": doc.content_md,
        "provenance": [
            {"source_file": f, "source_line_start": (doc.source_lines.get(f) or [None, None])[0], "source_line_end": (doc.source_lines.get(f) or [None, None])[1], "confidence": 1.0}
            for f in doc.source_files
        ],
    }


@router.post("/repos/{repo_id}/search")
async def docs_search(repo_id: int, req: SearchRequest, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("docs search requested", extra={"repo_id": repo_id, "event": "docs_search"})
    run = await _latest_run(session, repo_id, user)
    q = req.query.lower()

    artifacts = (await session.execute(select(Artifact).where(Artifact.run_id == run.id))).scalars().all()
    docs = (await session.execute(select(GeneratedDoc).where(GeneratedDoc.run_id == run.id))).scalars().all()

    hits = []
    for a in artifacts:
        score = 0
        if q in a.name.lower():
            score += 2
        if q in str(a.payload).lower():
            score += 1
        if score:
            hits.append({"type": "artifact", "id": a.artifact_id, "name": a.name, "score": score})

    for s in docs:
        score = 0
        if q in s.title.lower():
            score += 2
        if q in s.content_md.lower():
            score += 1
        if score:
            hits.append({"type": "doc", "id": s.artifact_id, "name": s.title, "score": score, "slug_path": s.slug_path})

    hits.sort(key=lambda x: x["score"], reverse=True)
    return {"results": hits[: req.top_k]}


@router.get("/repos/{repo_id}/artifacts/{artifact_id}")
async def artifact_get(repo_id: int, artifact_id: str, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("artifact requested", extra={"repo_id": repo_id, "event": "artifact_get"})
    run = await _latest_run(session, repo_id, user)
    artifact = (await session.execute(select(Artifact).where(Artifact.run_id == run.id, Artifact.artifact_id == artifact_id))).scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    return artifact


@router.get("/repos/{repo_id}/dependencies/{artifact_id}")
async def dependencies_get(repo_id: int, artifact_id: str, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("dependencies requested", extra={"repo_id": repo_id, "event": "dependencies_get"})
    run = await _latest_run(session, repo_id, user)
    edges = (await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == run.id, ArtifactEdge.src_artifact_id == artifact_id))).scalars().all()
    return {
        "artifact_id": artifact_id,
        "dependencies": [{"dst_artifact_id": e.dst_artifact_id, "kind": e.kind} for e in edges],
    }


@router.get("/repos/{repo_id}/runs/latest", response_model=RunResponse)
async def latest_run(repo_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("latest run requested", extra={"repo_id": repo_id, "event": "latest_run"})
    run = await _latest_run(session, repo_id, user)
    return RunResponse(
        run_id=run.id,
        repo_id=run.repo_id,
        status=run.status,
        stage=run.stage,
        progress=run.progress,
        error=run.error,
        quality_report=run.quality_report,
    )


@router.get("/repos/{repo_id}/artifacts")
async def artifacts_by_category(repo_id: int, category: str | None = None, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("artifacts requested", extra={"repo_id": repo_id, "event": "artifacts_by_category"})
    run = await _latest_run(session, repo_id, user)
    stmt = select(Artifact).where(Artifact.run_id == run.id)
    if category:
        stmt = stmt.where(Artifact.category == category)
    rows = (await session.execute(stmt.order_by(Artifact.category, Artifact.name))).scalars().all()
    return {
        "repo_id": repo_id,
        "run_id": run.id,
        "artifacts": [
            {
                "artifact_id": a.artifact_id,
                "category": a.category,
                "name": a.name,
                "source_file": a.source_file,
                "source_line_start": a.source_line_start,
                "source_line_end": a.source_line_end,
                "payload": a.payload,
            }
            for a in rows
        ],
    }


@router.get("/repos/{repo_id}/graph")
async def graph_get(
    repo_id: int,
    pr_run_id: int | None = None,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return a graph payload shaped for react-flow.

    If ``pr_run_id`` is provided, each node's tier (``Direct|High|Medium``)
    from the PR analysis run is attached, and edges that exist in base
    but not head are flagged ``broken: true`` for the dashed-red render.
    """
    logger.debug("graph requested", extra={"repo_id": repo_id, "pr_run_id": pr_run_id, "event": "graph_get"})
    run = await _latest_run(session, repo_id, user)
    head_run_id = run.id

    pr_run = None
    if pr_run_id is not None:
        pr_run = (
            await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.id == pr_run_id))
        ).scalars().first()
        if pr_run and pr_run.head_run_id:
            head_run_id = pr_run.head_run_id

    artifacts = (await session.execute(select(Artifact).where(Artifact.run_id == head_run_id))).scalars().all()
    edges = (await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == head_run_id))).scalars().all()

    tiers: dict[str, str] = {}
    broken_edges: set[tuple[str, str, str]] = set()
    if pr_run and pr_run.impact_summary:
        tiers = pr_run.impact_summary.get("tiers", {}) or {}
        # base-only edges = removed deps → render as dashed-red
        if pr_run.base_run_id:
            base_edges = (
                await session.execute(
                    select(ArtifactEdge).where(ArtifactEdge.run_id == pr_run.base_run_id)
                )
            ).scalars().all()
            head_edge_keys = {(e.src_artifact_id, e.dst_artifact_id, e.kind) for e in edges}
            for be in base_edges:
                key = (be.src_artifact_id, be.dst_artifact_id, be.kind)
                if key not in head_edge_keys:
                    broken_edges.add(key)

    nodes = []
    for a in artifacts:
        nodes.append(
            {
                "id": a.artifact_id,
                "category": a.category,
                "name": a.name,
                "source_file": a.source_file,
                "line": a.source_line_start,
                "tier": tiers.get(a.artifact_id),
                "language": (a.payload or {}).get("language"),
            }
        )

    edge_payload = [
        {
            "source": e.src_artifact_id,
            "target": e.dst_artifact_id,
            "kind": e.kind,
            "broken": False,
        }
        for e in edges
    ]
    for src, dst, kind in broken_edges:
        edge_payload.append({"source": src, "target": dst, "kind": kind, "broken": True})

    return {
        "repo_id": repo_id,
        "run_id": head_run_id,
        "pr_run_id": pr_run.id if pr_run else None,
        "tier_counts": (pr_run.impact_summary or {}).get("tier_counts") if pr_run else None,
        "nodes": nodes,
        "edges": edge_payload,
    }


@router.get("/repos/{repo_id}/generated-docs/{artifact_id}", response_model=GeneratedDocResponse)
async def generated_doc_get(repo_id: int, artifact_id: str, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("generated doc requested", extra={"repo_id": repo_id, "event": "generated_doc_get"})
    run = await _latest_run(session, repo_id, user)
    doc = (await session.execute(select(GeneratedDoc).where(GeneratedDoc.run_id == run.id, GeneratedDoc.artifact_id == artifact_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="doc_not_found")
    return {
        "artifact_id": doc.artifact_id,
        "category": doc.category,
        "title": doc.title,
        "slug_path": doc.slug_path,
        "content_hash": doc.content_hash,
        "source_files": doc.source_files,
        "source_lines": doc.source_lines,
        "content_md": doc.content_md,
    }


@router.get("/repos/{repo_id}/pull-requests")
async def pr_list(repo_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("pr list requested", extra={"repo_id": repo_id, "event": "pr_list"})
    await _user_repo(session, repo_id, user)
    prs = (await session.execute(select(PullRequest).where(PullRequest.repo_id == repo_id).order_by(PullRequest.number.desc()))).scalars().all()
    return {
        "pull_requests": [
            {
                "id": pr.id,
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "base_ref": pr.base_ref,
                "base_sha": pr.base_sha,
                "head_ref": pr.head_ref,
                "head_sha": pr.head_sha,
            }
            for pr in prs
        ]
    }


@router.get("/pull-requests/{pull_request_id}/impact")
async def pr_impact(pull_request_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("pr impact requested", extra={"pr_id": pull_request_id, "event": "pr_impact"})
    run = (await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.pull_request_id == pull_request_id).order_by(PrAnalysisRun.id.desc()))).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="pr_analysis_not_found")
    return {
        "pr_analysis_run_id": run.id,
        "status": run.status,
        "impact_summary": run.impact_summary,
        "review_comment_body": run.review_comment_body,
        "shadow_pr": (
            {
                "url": run.shadow_pr_url,
                "branch": run.shadow_pr_branch,
                "path": run.shadow_pr_path,
                "file_count": run.shadow_pr_file_count,
            }
            if run.shadow_pr_url
            else None
        ),
        "error": run.error,
    }


@router.get("/pull-requests/{pull_request_id}/doc-diff")
async def pr_doc_diff(pull_request_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("pr doc diff requested", extra={"pr_id": pull_request_id, "event": "pr_doc_diff"})
    run = (await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.pull_request_id == pull_request_id).order_by(PrAnalysisRun.id.desc()))).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="pr_analysis_not_found")
    diffs = (await session.execute(select(DocDiff).where(DocDiff.pr_analysis_run_id == run.id))).scalars().all()
    tier_order = {"Direct": 0, "High": 1, "Medium": 2}
    diffs_sorted = sorted(diffs, key=lambda d: (tier_order.get(d.impact_tier, 9), d.doc_path))
    return {
        "pr_analysis_run_id": run.id,
        "tier_counts": (run.impact_summary or {}).get("tier_counts") if run.impact_summary else None,
        "diffs": [
            {
                "artifact_id": d.artifact_id,
                "doc_path": d.doc_path,
                "change_type": d.change_type,
                "impact_tier": d.impact_tier,
                "affected_symbol_ids": d.affected_symbol_ids,
                "unified_diff": d.unified_diff,
                "side_by_side": d.side_by_side,
            }
            for d in diffs_sorted
        ],
    }


async def _user_repo(session: AsyncSession, repo_id: int, user: User) -> Repo:
    repo = (
        await session.execute(
            select(Repo).where(Repo.id == repo_id, Repo.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="repo_not_found")
    return repo


async def _latest_run(session: AsyncSession, repo_id: int, user: User) -> AnalysisRun:
    await _user_repo(session, repo_id, user)
    run = (await session.execute(select(AnalysisRun).where(AnalysisRun.repo_id == repo_id).order_by(AnalysisRun.id.desc()))).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="repo_or_docs_not_found")
    return run


def _diataxis_for_category(category: str) -> str:
    if category in {"project", "architecture", "flow"}:
        return "explanation"
    if category == "config":
        return "how-to"
    return "reference"
