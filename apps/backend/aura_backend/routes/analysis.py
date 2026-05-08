from __future__ import annotations
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionLocal, get_session
from ..deps import current_user
from ..models import GithubInstallation, GithubOAuthToken, Repo, AnalysisRun, DocSection, Artifact, ArtifactEdge, GeneratedDoc, PullRequest, PrAnalysisRun, DocDiff, User
from ..schemas import AnalyzeRepoRequest, AnalyzeRepoResponse, RunResponse, SearchRequest, DocSectionResponse, GeneratedDocResponse, DocChatRequest, DocChatResponse
from ..analysis.agents.docs_chat import answer_docs_question
from ..analysis.pipeline import _pipeline_llm_client
from ..services.github_app import (
    GithubAppError,
    build_app_jwt,
    create_installation_token,
    list_installation_repositories,
)
from ..services.github_oauth import list_user_repositories
from ..services.pr_orchestrator import run_pr_orchestrator
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


@router.post("/repos/{repo_id}/docs/chat", response_model=DocChatResponse)
async def docs_chat(repo_id: int, req: DocChatRequest, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("docs chat requested", extra={"repo_id": repo_id, "event": "docs_chat"})
    run = await _latest_run(session, repo_id, user)
    docs = (await session.execute(select(GeneratedDoc).where(GeneratedDoc.run_id == run.id))).scalars().all()
    llm = _pipeline_llm_client()
    return await answer_docs_question(llm, req, list(docs))


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
    canonical_run = await _latest_run(session, repo_id, user)
    canonical_run_id = canonical_run.id

    pr_run = None
    if pr_run_id is not None:
        pr_run = (
            await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.id == pr_run_id))
        ).scalars().first()

    canonical_artifacts = (
        await session.execute(select(Artifact).where(Artifact.run_id == canonical_run_id))
    ).scalars().all()
    canonical_edges = (
        await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == canonical_run_id))
    ).scalars().all()

    artifacts_by_id: dict[str, Artifact] = {a.artifact_id: a for a in canonical_artifacts}
    edge_keys: set[tuple[str, str, str]] = {(e.src_artifact_id, e.dst_artifact_id, e.kind) for e in canonical_edges}

    tiers: dict[str, str] = {}
    new_node_ids: set[str] = set()
    new_edges_set: set[tuple[str, str, str]] = set()
    broken_edges: set[tuple[str, str, str]] = set()

    overlay_artifacts: list[Artifact] = []
    overlay_edges: list[ArtifactEdge] = []

    if pr_run and pr_run.impact_summary:
        tiers = pr_run.impact_summary.get("tiers", {}) or {}
        added_ids = {a.get("artifact_id") for a in (pr_run.impact_summary.get("added") or []) if a.get("artifact_id")}
        if pr_run.head_run_id:
            head_arts = (
                await session.execute(select(Artifact).where(Artifact.run_id == pr_run.head_run_id))
            ).scalars().all()
            head_edges = (
                await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == pr_run.head_run_id))
            ).scalars().all()
            head_edge_keys = {(e.src_artifact_id, e.dst_artifact_id, e.kind) for e in head_edges}
            new_edges_set = head_edge_keys - edge_keys
            for ha in head_arts:
                if ha.artifact_id in added_ids and ha.artifact_id not in artifacts_by_id:
                    overlay_artifacts.append(ha)
                    new_node_ids.add(ha.artifact_id)
            for he in head_edges:
                key = (he.src_artifact_id, he.dst_artifact_id, he.kind)
                if key in new_edges_set:
                    overlay_edges.append(he)
        if pr_run.base_run_id:
            base_edges_rows = (
                await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == pr_run.base_run_id))
            ).scalars().all()
            base_edge_keys = {(e.src_artifact_id, e.dst_artifact_id, e.kind) for e in base_edges_rows}
            head_edge_keys2 = {
                (e.src_artifact_id, e.dst_artifact_id, e.kind)
                for e in (
                    await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == pr_run.head_run_id))
                ).scalars().all()
            } if pr_run.head_run_id else set()
            broken_edges = base_edge_keys - head_edge_keys2

    nodes = []
    for a in canonical_artifacts:
        nodes.append(
            {
                "id": a.artifact_id,
                "category": a.category,
                "name": a.name,
                "source_file": a.source_file,
                "line": a.source_line_start,
                "tier": tiers.get(a.artifact_id),
                "language": (a.payload or {}).get("language"),
                "is_new": False,
            }
        )
    # Append PR-only added nodes (overlay; not merged into canonical until PR merge).
    for a in overlay_artifacts:
        nodes.append(
            {
                "id": a.artifact_id,
                "category": a.category,
                "name": a.name,
                "source_file": a.source_file,
                "line": a.source_line_start,
                "tier": tiers.get(a.artifact_id, "Direct"),
                "language": (a.payload or {}).get("language"),
                "is_new": True,
            }
        )

    edge_payload = [
        {
            "source": e.src_artifact_id,
            "target": e.dst_artifact_id,
            "kind": e.kind,
            "broken": False,
            "is_new": False,
        }
        for e in canonical_edges
    ]
    for e in overlay_edges:
        edge_payload.append(
            {
                "source": e.src_artifact_id,
                "target": e.dst_artifact_id,
                "kind": e.kind,
                "broken": False,
                "is_new": True,
            }
        )
    for src, dst, kind in broken_edges:
        edge_payload.append({"source": src, "target": dst, "kind": kind, "broken": True, "is_new": False})

    return {
        "repo_id": repo_id,
        "run_id": canonical_run_id,
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
    pr_ids = [pr.id for pr in prs]
    runs_by_pr: dict[int, PrAnalysisRun] = {}
    if pr_ids:
        runs = (
            await session.execute(
                select(PrAnalysisRun).where(PrAnalysisRun.pull_request_id.in_(pr_ids)).order_by(PrAnalysisRun.id.desc())
            )
        ).scalars().all()
        for run in runs:
            runs_by_pr.setdefault(run.pull_request_id, run)
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
                "html_url": pr.html_url,
                "merged": bool(pr.merged),
                "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
                "latest_pr_run": _pr_run_summary(runs_by_pr.get(pr.id)),
            }
            for pr in prs
        ]
    }


def _pr_run_summary(run: PrAnalysisRun | None) -> dict | None:
    if not run:
        return None
    flags = run.mismatch_flags or {}
    mismatch_count = (
        len(flags.get("undocumented_endpoint") or [])
        + len(flags.get("undocumented_data_model") or [])
        + len(flags.get("direct_or_high_doc_diff") or [])
    )
    return {
        "id": run.id,
        "status": run.status,
        "tier_counts": (run.impact_summary or {}).get("tier_counts") if run.impact_summary else None,
        "mismatch_flag_count": mismatch_count,
        "has_mismatch": bool(flags.get("any")),
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


@router.get("/pull-requests/{pull_request_id}/code-diff")
async def pr_code_diff(pull_request_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("pr code-diff requested", extra={"pr_id": pull_request_id, "event": "pr_code_diff"})
    run = (
        await session.execute(
            select(PrAnalysisRun).where(PrAnalysisRun.pull_request_id == pull_request_id).order_by(PrAnalysisRun.id.desc())
        )
    ).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="pr_analysis_not_found")
    patches = run.code_patches or {}
    return {
        "pr_analysis_run_id": run.id,
        "patches": patches,
        "files_changed": sorted(patches.keys()),
    }


@router.get("/pull-requests/{pull_request_id}/affected-docs")
async def pr_affected_docs(pull_request_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    """Ordered list of affected docs powering prev/next navigation in the immersive PR review."""
    logger.debug("pr affected docs requested", extra={"pr_id": pull_request_id, "event": "pr_affected_docs"})
    run = (
        await session.execute(
            select(PrAnalysisRun).where(PrAnalysisRun.pull_request_id == pull_request_id).order_by(PrAnalysisRun.id.desc())
        )
    ).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="pr_analysis_not_found")
    diffs = (await session.execute(select(DocDiff).where(DocDiff.pr_analysis_run_id == run.id))).scalars().all()
    head_run_id = run.head_run_id
    artifact_ids = [d.artifact_id for d in diffs]
    source_by_artifact: dict[str, list[str]] = {}
    if head_run_id and artifact_ids:
        artifacts = (
            await session.execute(
                select(Artifact).where(Artifact.run_id == head_run_id, Artifact.artifact_id.in_(artifact_ids))
            )
        ).scalars().all()
        for a in artifacts:
            if a.source_file:
                source_by_artifact.setdefault(a.artifact_id, []).append(a.source_file)
    tier_order = {"Direct": 0, "High": 1, "Medium": 2}
    items = sorted(
        diffs,
        key=lambda d: (tier_order.get(d.impact_tier, 9), d.doc_path),
    )
    return {
        "pr_analysis_run_id": run.id,
        "items": [
            {
                "artifact_id": d.artifact_id,
                "doc_path": d.doc_path,
                "impact_tier": d.impact_tier,
                "change_type": d.change_type,
                "source_files": source_by_artifact.get(d.artifact_id, []),
            }
            for d in items
        ],
    }


@router.post("/pull-requests/{pull_request_id}/re-analyze")
async def pr_re_analyze(
    pull_request_id: int,
    background: BackgroundTasks,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    """Fire the PR orchestrator again for an existing PR, in the background."""
    logger.info("pr re-analyze requested", extra={"pr_id": pull_request_id, "event": "pr_re_analyze"})
    pr = (await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))).scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="pr_not_found")
    repo = (
        await session.execute(select(Repo).where(Repo.id == pr.repo_id, Repo.user_id == user.id))
    ).scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="pr_not_found")
    background.add_task(run_pr_orchestrator, SessionLocal, pull_request_id)
    return {"status": "queued", "pull_request_id": pull_request_id}


@router.post("/repos/{repo_id}/re-analyze")
async def repo_re_analyze(
    repo_id: int,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    """Kick off a fresh canonical AnalysisRun on the repo's default branch."""
    logger.info("repo re-analyze requested", extra={"repo_id": repo_id, "event": "repo_re_analyze"})
    repo = await _user_repo(session, repo_id, user)
    run = AnalysisRun(
        repo_id=repo.id,
        user_id=user.id,
        status="queued",
        stage="queued",
        progress=0,
        branch=repo.default_branch,
        commit_sha="",
    )
    session.add(run)
    await session.commit()
    from ..main import app_state
    await app_state.queue.start()
    await app_state.queue.enqueue(run.id)
    return {"status": "queued", "run_id": run.id, "repo_id": repo.id}


@router.get("/pull-requests/{pull_request_id}/impact")
async def pr_impact(pull_request_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("pr impact requested", extra={"pr_id": pull_request_id, "event": "pr_impact"})
    run = (await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.pull_request_id == pull_request_id).order_by(PrAnalysisRun.id.desc()))).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="pr_analysis_not_found")
    pr = (await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))).scalar_one_or_none()
    return {
        "pr_analysis_run_id": run.id,
        "status": run.status,
        "impact_summary": run.impact_summary,
        "review_comment_body": run.review_comment_body,
        "mismatch_flags": run.mismatch_flags,
        "dashboard_url": run.dashboard_url,
        "pull_request": (
            {
                "id": pr.id,
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "merged": bool(pr.merged),
                "html_url": pr.html_url,
                "base_ref": pr.base_ref,
                "head_ref": pr.head_ref,
            }
            if pr
            else None
        ),
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
    repo = await _user_repo(session, repo_id, user)
    run = (
        await session.execute(
            select(AnalysisRun)
            .where(
                AnalysisRun.repo_id == repo_id,
                AnalysisRun.is_pr_run.is_(False),
                AnalysisRun.branch == repo.default_branch,
                AnalysisRun.status == "succeeded",
            )
            .order_by(AnalysisRun.id.desc())
        )
    ).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="repo_or_docs_not_found")
    return run


def _diataxis_for_category(category: str) -> str:
    if category in {"project", "architecture", "flow"}:
        return "explanation"
    if category == "config":
        return "how-to"
    return "reference"
