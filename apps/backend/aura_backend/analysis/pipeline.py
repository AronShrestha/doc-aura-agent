from __future__ import annotations

import io
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..config import BASE_DIR, settings
from ..models import (
    AnalysisRun,
    Artifact,
    ArtifactEdge,
    DocMapping,
    GeneratedDoc,
    GithubOAuthToken,
    Repo,
)
from ..services.github_app import build_app_jwt, create_installation_token
from .agents.clients import DisabledVisionClient, OpenAIChatClient, OpenAIVisionClient
from .agents.orchestrator import run_documentation_agents
from .docs import write_docs
from .extractors import extract_repo
from .snapshot import build_snapshot
from .types import AnalysisResult, ExtractedArtifact, ExtractedEdge, GeneratedDocDraft


logger = logging.getLogger(__name__)

STAGES = [
    ("acquire", 10),
    ("parse", 25),
    ("extract", 50),
    ("synthesize", 75),
    ("persist", 95),
]

CHECKOUT_ROOT = BASE_DIR / ".aura" / "checkouts"


async def _set_stage(session_factory: async_sessionmaker, run_id: int, stage: str, progress: int) -> None:
    logger.info("analysis stage started", extra={"run_id": run_id, "stage": stage})
    async with session_factory() as session:
        run = (await session.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalar_one()
        run.stage = stage
        run.progress = progress
        await session.commit()


async def run_analysis(run_id: int, session_factory: async_sessionmaker) -> None:
    logger.info("analysis run starting", extra={"run_id": run_id})
    try:
        async with session_factory() as session:
            run = (await session.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalar_one()
            run.status = "running"
            run.stage = "acquire"
            run.progress = 2
            await session.commit()

        result: AnalysisResult | None = None
        for stage, progress in STAGES:
            await _set_stage(session_factory, run_id, stage, progress)
            if stage == "acquire":
                root, repo, run = await _acquire_checkout(session_factory, run_id)
            elif stage == "parse":
                snapshot = build_snapshot(root, repo.id, run.commit_sha or run.branch)
                logger.info(
                    "snapshot built",
                    extra={"run_id": run_id, "repo_id": repo.id, "stage": "parse"},
                )
            elif stage == "extract":
                artifacts, edges, summary = extract_repo(snapshot)
                logger.info(
                    "artifacts extracted",
                    extra={"run_id": run_id, "repo_id": repo.id, "stage": "extract"},
                )
            elif stage == "synthesize":
                llm_client = _pipeline_llm_client()
                vlm_client = _pipeline_vlm_client()
                docs, quality = await run_documentation_agents(
                    snapshot,
                    artifacts,
                    edges,
                    summary,
                    llm_client,
                    vlm_client,
                    vlm_enabled=settings.vlm_enabled,
                    max_artifacts=settings.agent_max_artifacts,
                )
                manifest = quality.pop("manifest")
                write_docs(root, docs, manifest)
                logger.info(
                    "agent docs generated",
                    extra={"run_id": run_id, "repo_id": repo.id, "stage": "synthesize"},
                )
                result = AnalysisResult(snapshot=snapshot, artifacts=artifacts, edges=edges, docs=docs, manifest=manifest, quality_report=quality)
            elif stage == "persist":
                if result is None:
                    raise RuntimeError("analysis_result_missing")
                await _persist_result(session_factory, run_id, result)
                logger.info("analysis run succeeded", extra={"run_id": run_id, "repo_id": repo.id, "stage": "done"})
    except Exception as exc:
        logger.exception("analysis run failed", extra={"run_id": run_id})
        async with session_factory() as session:
            run = (await session.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalar_one_or_none()
            if run:
                run.status = "failed"
                run.stage = run.stage or "failed"
                run.progress = 100
                run.error = str(exc)
                await session.commit()


async def run_static_analysis_for_ref(
    session_factory: async_sessionmaker,
    repo_id: int,
    ref: str,
    commit_sha: str = "",
) -> int:
    logger.info("static analysis for ref queued", extra={"repo_id": repo_id, "stage": "pr_ref_analysis"})
    async with session_factory() as session:
        repo = (await session.execute(select(Repo).where(Repo.id == repo_id))).scalar_one()
        run = AnalysisRun(
            repo_id=repo.id,
            status="queued",
            stage="queued",
            progress=0,
            branch=ref,
            commit_sha=commit_sha or ref,
        )
        session.add(run)
        await session.commit()
        run_id = run.id
    await run_analysis(run_id, session_factory)
    return run_id


async def _acquire_checkout(session_factory: async_sessionmaker, run_id: int) -> tuple[Path, Repo, AnalysisRun]:
    async with session_factory() as session:
        run = (await session.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalar_one()
        repo = (await session.execute(select(Repo).where(Repo.id == run.repo_id))).scalar_one()
        token = await _repo_token(session_factory, repo)
    root = await _fetch_repo_zip(repo, run, token)
    logger.info("checkout acquired", extra={"run_id": run_id, "repo_id": repo.id, "stage": "acquire"})
    return root, repo, run


async def _repo_token(session_factory: async_sessionmaker, repo: Repo) -> str:
    if repo.installation_id and repo.installation_id != "oauth":
        app_jwt = build_app_jwt(settings.github_app_id, settings.github_app_private_key)
        return await create_installation_token(app_jwt, repo.installation_id)
    async with session_factory() as session:
        token_row = (await session.execute(select(GithubOAuthToken).order_by(GithubOAuthToken.id.desc()))).scalars().first()
    if token_row is None:
        raise RuntimeError("oauth_token_missing")
    return token_row.access_token


async def _fetch_repo_zip(repo: Repo, run: AnalysisRun, token: str) -> Path:
    ref = run.commit_sha or run.branch or repo.default_branch or "main"
    url = f"https://api.github.com/repos/{repo.owner}/{repo.name}/zipball/{ref}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        content = resp.content
    logger.info("github zip fetched", extra={"run_id": run.id, "repo_id": repo.id, "stage": "acquire"})

    checkout = CHECKOUT_ROOT / str(repo.id) / str(run.id)
    if checkout.exists():
        shutil.rmtree(checkout)
    checkout.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        zf.extractall(checkout)
    children = [p for p in checkout.iterdir() if p.is_dir()]
    if not children:
        raise RuntimeError("zip_extract_failed")
    extracted = children[0]
    root = checkout / "repo"
    if root.exists():
        shutil.rmtree(root)
    extracted.rename(root)
    return root


async def _llm_chat(messages: list[dict[str, str]]) -> str:
    logger.debug("llm chat transport called", extra={"stage": "llm_transport"})
    return await OpenAIChatClient(
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_api_key,
        settings.llm_timeout_seconds,
        settings.llm_max_tokens,
    ).complete(messages)


class PipelineLLMClient:
    async def complete(self, messages, *, max_tokens=None, temperature=0.2):
        return await _llm_chat(messages)


def _pipeline_llm_client():
    return PipelineLLMClient()


def _pipeline_vlm_client():
    if not settings.vlm_enabled:
        return DisabledVisionClient()
    return OpenAIVisionClient(
        settings.vlm_base_url,
        settings.vlm_model,
        settings.vlm_api_key,
        settings.vlm_timeout_seconds,
        settings.vlm_max_tokens,
    )


async def _persist_result(session_factory: async_sessionmaker, run_id: int, result: AnalysisResult) -> None:
    logger.info(
        "persisting analysis result",
        extra={"run_id": run_id, "repo_id": result.snapshot.repo_id, "stage": "persist"},
    )
    async with session_factory() as session:
        run = (await session.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalar_one()
        await session.execute(delete(Artifact).where(Artifact.run_id == run.id))
        await session.execute(delete(ArtifactEdge).where(ArtifactEdge.run_id == run.id))
        await session.execute(delete(GeneratedDoc).where(GeneratedDoc.run_id == run.id))
        await session.execute(delete(DocMapping).where(DocMapping.run_id == run.id))

        session.add_all([_artifact_row(run.id, artifact) for artifact in result.artifacts])
        session.add_all([_edge_row(run.id, edge) for edge in result.edges])
        session.add_all([_doc_row(run.id, doc) for doc in result.docs])
        session.add_all([_mapping_row(run.id, doc) for doc in result.docs])
        run.status = "succeeded"
        run.stage = "done"
        run.progress = 100
        run.error = None
        run.quality_report = result.quality_report
        await session.commit()


def _artifact_row(run_id: int, artifact: ExtractedArtifact) -> Artifact:
    return Artifact(
        run_id=run_id,
        artifact_id=artifact.artifact_id,
        category=artifact.category,
        name=artifact.name,
        source_file=artifact.source_file,
        source_line_start=artifact.source_line_start,
        source_line_end=artifact.source_line_end,
        payload={
            **artifact.payload,
            "canonical_locator": artifact.canonical_locator,
            "content_hash": artifact.payload.get("source_hash", ""),
        },
    )


def _edge_row(run_id: int, edge: ExtractedEdge) -> ArtifactEdge:
    return ArtifactEdge(
        run_id=run_id,
        src_artifact_id=edge.src_artifact_id,
        dst_artifact_id=edge.dst_artifact_id,
        kind=edge.kind,
    )


def _doc_row(run_id: int, doc: GeneratedDocDraft) -> GeneratedDoc:
    return GeneratedDoc(
        run_id=run_id,
        artifact_id=doc.artifact_id,
        category=doc.category,
        title=doc.title,
        slug_path=doc.slug_path,
        content_hash=doc.content_hash,
        generated_sha=doc.content_hash,
        last_verified_sha=doc.content_hash,
        source_files=doc.source_files,
        source_lines=doc.source_lines,
        content_md=doc.content_md,
    )


def _mapping_row(run_id: int, doc: GeneratedDocDraft) -> DocMapping:
    return DocMapping(
        run_id=run_id,
        artifact_id=doc.artifact_id,
        doc_path=doc.slug_path,
        content_hash=doc.content_hash,
    )


def docs_manifest_from_rows(docs: list[GeneratedDoc]) -> dict[str, Any]:
    return {
        "docs": {
            doc.artifact_id: {
                "path": doc.slug_path,
                "category": doc.category,
                "title": doc.title,
                "content_hash": doc.content_hash,
                "source_files": doc.source_files,
            }
            for doc in docs
        }
    }
