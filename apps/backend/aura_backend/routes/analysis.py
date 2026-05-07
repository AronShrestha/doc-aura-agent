from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import SessionLocal, get_session
from ..models import AnalysisRun, Artifact, ArtifactEdge, DocDiff, GeneratedDoc, GithubInstallation, GithubOAuthToken, PrAnalysisRun, PullRequest, Repo
from ..routes.auth import current_user
from ..schemas import AnalyzeRepoRequest, AnalyzeRepoResponse, DocSectionResponse, GeneratedDocResponse, RunResponse, SearchRequest
from ..services.github_app import (
    GithubAppError,
    build_app_jwt,
    create_installation_token,
    list_installation_repositories,
)
from ..services.github_prs import create_or_update_docs_followup_pr, post_or_update_review_comment
from ..services.github_oauth import list_user_repositories
from ..services.pr_analysis import analyze_pull_request

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
            Repo.github_repo_id == req.github_repo_id,
            Repo.installation_id == (installation_id or "oauth"),
        )
    )).scalar_one_or_none()
    if not repo:
        repo = Repo(
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
    run = (await session.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="run_not_found")
    return RunResponse(
        run_id=run.id,
        repo_id=run.repo_id,
        status=run.status,
        stage=run.stage,
        progress=run.progress,
        error=run.error,
        quality_report=run.quality_report,
    )


@router.get("/repos/{repo_id}/docs/index")
async def docs_index(repo_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("docs index requested", extra={"repo_id": repo_id, "event": "docs_index"})
    run = await _latest_run(session, repo_id)
    docs = (await session.execute(select(GeneratedDoc).where(GeneratedDoc.run_id == run.id).order_by(GeneratedDoc.slug_path))).scalars().all()
    return {
        "repo_id": repo_id,
        "run_id": run.id,
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
    run = await _latest_run(session, repo_id)
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
    run = await _latest_run(session, repo_id)
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
    run = await _latest_run(session, repo_id)
    artifact = (await session.execute(select(Artifact).where(Artifact.run_id == run.id, Artifact.artifact_id == artifact_id))).scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="artifact_not_found")
    return artifact


@router.get("/repos/{repo_id}/dependencies/{artifact_id}")
async def dependencies_get(repo_id: int, artifact_id: str, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("dependencies requested", extra={"repo_id": repo_id, "event": "dependencies_get"})
    run = await _latest_run(session, repo_id)
    edges = (await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == run.id, ArtifactEdge.src_artifact_id == artifact_id))).scalars().all()
    return {
        "artifact_id": artifact_id,
        "dependencies": [{"dst_artifact_id": e.dst_artifact_id, "kind": e.kind} for e in edges],
    }


@router.get("/repos/{repo_id}/runs/latest", response_model=RunResponse)
async def latest_run(repo_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("latest run requested", extra={"repo_id": repo_id, "event": "latest_run"})
    run = await _latest_run(session, repo_id)
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
    run = await _latest_run(session, repo_id)
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
async def graph_get(repo_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("graph requested", extra={"repo_id": repo_id, "event": "graph_get"})
    run = await _latest_run(session, repo_id)
    artifacts = (await session.execute(select(Artifact).where(Artifact.run_id == run.id))).scalars().all()
    edges = (await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == run.id))).scalars().all()
    return {
        "repo_id": repo_id,
        "run_id": run.id,
        "nodes": [{"id": a.artifact_id, "category": a.category, "name": a.name} for a in artifacts],
        "edges": [{"source": e.src_artifact_id, "target": e.dst_artifact_id, "kind": e.kind} for e in edges],
    }


@router.get("/repos/{repo_id}/generated-docs/{artifact_id}", response_model=GeneratedDocResponse)
async def generated_doc_get(repo_id: int, artifact_id: str, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("generated doc requested", extra={"repo_id": repo_id, "event": "generated_doc_get"})
    run = await _latest_run(session, repo_id)
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


@router.post("/pull-requests/{pull_request_id}/analyze")
async def pr_analyze(pull_request_id: int, user=Depends(current_user)):
    logger.info("manual pr analysis requested", extra={"pr_id": pull_request_id, "event": "pr_analyze"})
    try:
        await analyze_pull_request(SessionLocal, pull_request_id)
        await post_or_update_review_comment(SessionLocal, pull_request_id)
    except NoResultFound as exc:
        raise HTTPException(status_code=404, detail="pull_request_not_found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="pr_analysis_failed") from exc

    async with SessionLocal() as session:
        run = (
            await session.execute(
                select(PrAnalysisRun).where(PrAnalysisRun.pull_request_id == pull_request_id).order_by(PrAnalysisRun.id.desc())
            )
        ).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="pr_analysis_not_found")
    return _serialize_pr_analysis_run(run)


@router.get("/pull-requests/{pull_request_id}/impact")
async def pr_impact(pull_request_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("pr impact requested", extra={"pr_id": pull_request_id, "event": "pr_impact"})
    run = (await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.pull_request_id == pull_request_id).order_by(PrAnalysisRun.id.desc()))).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="pr_analysis_not_found")
    return _serialize_pr_analysis_run(run)


@router.post("/pull-requests/{pull_request_id}/documentation-pr")
async def pr_documentation_pr(pull_request_id: int, user=Depends(current_user)):
    logger.info("manual docs follow-up requested", extra={"pr_id": pull_request_id, "event": "pr_docs_followup"})
    try:
        result = await create_or_update_docs_followup_pr(SessionLocal, pull_request_id)
    except NoResultFound as exc:
        raise HTTPException(status_code=404, detail="pull_request_not_found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="docs_followup_failed") from exc
    return result


@router.get("/pull-requests/{pull_request_id}/doc-diff")
async def pr_doc_diff(pull_request_id: int, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("pr doc diff requested", extra={"pr_id": pull_request_id, "event": "pr_doc_diff"})
    run = (await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.pull_request_id == pull_request_id).order_by(PrAnalysisRun.id.desc()))).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="pr_analysis_not_found")
    diffs = (await session.execute(select(DocDiff).where(DocDiff.pr_analysis_run_id == run.id))).scalars().all()
    return {
        "pr_analysis_run_id": run.id,
        "diffs": [
            {
                "artifact_id": d.artifact_id,
                "doc_path": d.doc_path,
                "change_type": d.change_type,
                "unified_diff": d.unified_diff,
                "side_by_side": d.side_by_side,
            }
            for d in diffs
        ],
    }


async def _latest_run(session: AsyncSession, repo_id: int) -> AnalysisRun:
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


def _serialize_pr_analysis_run(run: PrAnalysisRun) -> dict:
    return {
        "pr_analysis_run_id": run.id,
        "status": run.status,
        "impact_summary": run.impact_summary,
        "review_comment_body": run.review_comment_body,
        "error": run.error,
    }
