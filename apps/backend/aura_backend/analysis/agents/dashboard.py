"""Dashboard Agent.

Enriches the PR-analysis impact summary with:
1. Per-file unified diff patches fetched from GitHub Compare API.
2. ``mismatch_flags`` describing places where docs lag behind code:
   - new endpoints with no generated doc
   - new data models with no generated doc
   - any DocDiff row with Direct/High impact tier

The output is consumed by the PR Orchestrator to (a) persist a richer
``PrAnalysisRun`` payload that the frontend renders, and (b) decide
whether the comment agent should attach a mismatch warning.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ...config import settings
from ...models import GeneratedDoc, GithubOAuthToken, PullRequest, Repo
from ...services.github_app import GithubAppError, build_app_jwt, create_installation_token


logger = logging.getLogger(__name__)


async def run_dashboard_agent(
    session_factory: async_sessionmaker,
    pull_request_id: int,
    impact: dict[str, Any],
    doc_diffs: list[dict[str, Any]],
    head_run_id: int,
) -> dict[str, Any]:
    logger.info("dashboard agent started", extra={"pr_id": pull_request_id, "agent": "dashboard"})
    async with session_factory() as session:
        pr = (await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))).scalar_one()
        repo = (await session.execute(select(Repo).where(Repo.id == pr.repo_id))).scalar_one()
        head_doc_artifact_ids = {
            row[0]
            for row in (
                await session.execute(
                    select(GeneratedDoc.artifact_id).where(GeneratedDoc.run_id == head_run_id)
                )
            ).all()
        }
        token = await _resolve_token(session, repo)

    affected_files = _collect_affected_files(impact)
    code_patches: dict[str, str] = {}
    if token and affected_files:
        try:
            patches = await _fetch_compare_patches(token, repo, pr.base_sha, pr.head_sha)
            code_patches = {f: p for f, p in patches.items() if f in affected_files}
        except Exception as exc:
            logger.warning(
                "dashboard agent compare fetch failed",
                extra={"pr_id": pull_request_id, "error": str(exc)},
            )

    mismatch_flags = _compute_mismatch_flags(impact, doc_diffs, head_doc_artifact_ids)
    logger.info(
        "dashboard agent done",
        extra={
            "pr_id": pull_request_id,
            "agent": "dashboard",
            "patch_files": len(code_patches),
            "mismatch": {k: len(v) if isinstance(v, list) else bool(v) for k, v in mismatch_flags.items()},
        },
    )
    return {"code_patches": code_patches, "mismatch_flags": mismatch_flags}


def _collect_affected_files(impact: dict[str, Any]) -> set[str]:
    files: set[str] = set()
    for bucket in ("added", "modified", "removed"):
        for art in impact.get(bucket, []) or []:
            sf = art.get("source_file")
            if sf:
                files.add(sf)
    return files


def _compute_mismatch_flags(
    impact: dict[str, Any],
    doc_diffs: list[dict[str, Any]],
    head_doc_artifact_ids: set[str],
) -> dict[str, Any]:
    undocumented_endpoint = [
        a for a in (impact.get("added") or []) if a.get("category") == "endpoint" and a.get("artifact_id") not in head_doc_artifact_ids
    ]
    undocumented_data_model = [
        a for a in (impact.get("added") or []) if a.get("category") == "data_model" and a.get("artifact_id") not in head_doc_artifact_ids
    ]
    direct_or_high = [
        d for d in doc_diffs if d.get("impact_tier") in ("Direct", "High")
    ]
    return {
        "undocumented_endpoint": undocumented_endpoint,
        "undocumented_data_model": undocumented_data_model,
        "direct_or_high_doc_diff": direct_or_high,
        "any": bool(undocumented_endpoint or undocumented_data_model or direct_or_high),
    }


async def _resolve_token(session, repo: Repo) -> str | None:
    if repo.installation_id and repo.installation_id != "oauth":
        try:
            app_jwt = build_app_jwt(settings.github_app_id, settings.github_app_private_key)
            return await create_installation_token(app_jwt, repo.installation_id)
        except GithubAppError as exc:
            logger.warning("installation token failed", extra={"repo_id": repo.id, "error": str(exc)})
    token_row = (
        await session.execute(select(GithubOAuthToken).order_by(GithubOAuthToken.id.desc()))
    ).scalars().first()
    return token_row.access_token if token_row else None


async def _fetch_compare_patches(
    token: str, repo: Repo, base_sha: str, head_sha: str
) -> dict[str, str]:
    url = f"https://api.github.com/repos/{repo.owner}/{repo.name}/compare/{base_sha}...{head_sha}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(f"compare_failed:{resp.status_code}:{resp.text[:200]}")
    files = resp.json().get("files") or []
    return {f["filename"]: f.get("patch") or "" for f in files}
