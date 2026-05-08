from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import PullRequest, Repo
from ..services.pr_orchestrator import run_pr_orchestrator

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
):
    logger.info("github webhook received", extra={"event": "github_webhook"})
    body = await request.body()
    _verify_signature(body, x_hub_signature_256)
    payload = await request.json()
    if x_github_event != "pull_request":
        logger.info("github webhook ignored", extra={"event": "github_webhook_ignored"})
        return {"status": "ignored", "event": x_github_event}
    action = payload.get("action")
    pr_payload = payload.get("pull_request") or {}
    base_ref = (pr_payload.get("base") or {}).get("ref") or ""
    repo_payload = payload.get("repository") or {}
    default_branch = repo_payload.get("default_branch") or "main"
    if base_ref != default_branch:
        logger.info(
            "pull request webhook ignored; base != default branch",
            extra={"event": "github_webhook_ignored", "base_ref": base_ref, "default_branch": default_branch},
        )
        return {"status": "ignored", "reason": "base_not_default", "base_ref": base_ref}

    if action == "closed" and pr_payload.get("merged"):
        pr_id = await _upsert_pr(payload)
        promoted = await _promote_on_merge(pr_id)
        logger.info("pull request merged; head run promoted", extra={"pr_id": pr_id, "promoted_run_id": promoted})
        return {"status": "merged", "pull_request_id": pr_id, "promoted_run_id": promoted}

    if action not in {"opened", "synchronize", "reopened"}:
        logger.info("pull request webhook action ignored", extra={"event": "github_webhook_ignored", "action": action})
        return {"status": "ignored", "action": action}

    pr_id = await _upsert_pr(payload)
    logger.info("pull request webhook accepted", extra={"pr_id": pr_id, "event": "github_webhook_accepted"})
    await run_pr_orchestrator(SessionLocal, pr_id)
    return {"status": "accepted", "pull_request_id": pr_id}


async def _promote_on_merge(pull_request_id: int) -> int | None:
    """On PR merge into default branch: take the LLM-updated docs cached in
    DocDiff rows and write them into the canonical (non-PR) AnalysisRun's
    GeneratedDoc table. Original docs were untouched until now; this is the
    moment they update."""
    import hashlib
    from ..models import AnalysisRun, DocDiff, GeneratedDoc, PrAnalysisRun, PullRequest

    async with SessionLocal() as session:
        pr = (await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))).scalar_one_or_none()
        if not pr:
            return None
        pr_run = (
            await session.execute(
                select(PrAnalysisRun)
                .where(PrAnalysisRun.pull_request_id == pull_request_id)
                .order_by(PrAnalysisRun.id.desc())
            )
        ).scalars().first()
        if not pr_run:
            return None
        repo = (await session.execute(select(Repo).where(Repo.id == pr.repo_id))).scalar_one()
        canonical = (
            await session.execute(
                select(AnalysisRun)
                .where(
                    AnalysisRun.repo_id == pr.repo_id,
                    AnalysisRun.is_pr_run.is_(False),
                    AnalysisRun.status == "succeeded",
                    AnalysisRun.branch == repo.default_branch,
                )
                .order_by(AnalysisRun.id.desc())
            )
        ).scalars().first()
        if not canonical:
            logger.warning("merge: no canonical run; skipping doc promotion", extra={"pr_id": pull_request_id})
            return None
        diffs = (
            await session.execute(select(DocDiff).where(DocDiff.pr_analysis_run_id == pr_run.id))
        ).scalars().all()
        canonical_docs = (
            await session.execute(select(GeneratedDoc).where(GeneratedDoc.run_id == canonical.id))
        ).scalars().all()
        canonical_by_aid = {d.artifact_id: d for d in canonical_docs}
        applied = 0
        for diff in diffs:
            doc = canonical_by_aid.get(diff.artifact_id)
            if not doc:
                continue
            after_text = _extract_head_text(diff.side_by_side)
            if not after_text:
                continue
            if after_text == (doc.content_md or ""):
                continue
            doc.content_md = after_text
            doc.content_hash = hashlib.sha256(after_text.encode("utf-8")).hexdigest()
            applied += 1
        if applied:
            await session.commit()
        logger.info("merge: docs promoted", extra={"pr_id": pull_request_id, "applied": applied, "canonical_run_id": canonical.id})
        return canonical.id


def _extract_head_text(side_by_side: dict | None) -> str:
    if not side_by_side or not side_by_side.get("rows"):
        return ""
    out: list[str] = []
    for row in side_by_side["rows"]:
        for ln in row.get("head") or []:
            out.append(ln)
    return "\n".join(out)


def _verify_signature(body: bytes, signature: str | None) -> None:
    if not settings.github_webhook_secret:
        raise HTTPException(status_code=500, detail="github_webhook_secret_not_configured")
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="invalid_signature")
    digest = hmac.new(settings.github_webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(f"sha256={digest}", signature):
        raise HTTPException(status_code=401, detail="invalid_signature")
    logger.info("github webhook signature verified", extra={"event": "github_webhook_signature"})


async def _upsert_pr(payload: dict) -> int:
    repo_payload = payload["repository"]
    pr_payload = payload["pull_request"]
    async with SessionLocal() as session:
        repo = (await session.execute(select(Repo).where(Repo.github_repo_id == str(repo_payload["id"])))).scalar_one_or_none()
        if not repo:
            repo = Repo(
                github_repo_id=str(repo_payload["id"]),
                full_name=repo_payload["full_name"],
                default_branch=repo_payload.get("default_branch", "main"),
                installation_id=str((payload.get("installation") or {}).get("id") or "oauth"),
                owner=repo_payload["owner"]["login"],
                name=repo_payload["name"],
            )
            session.add(repo)
            await session.flush()
        pr = (await session.execute(select(PullRequest).where(PullRequest.repo_id == repo.id, PullRequest.number == int(pr_payload["number"])))).scalar_one_or_none()
        if not pr:
            pr = PullRequest(repo_id=repo.id, github_pr_id=str(pr_payload["id"]), number=int(pr_payload["number"]))
            session.add(pr)
        pr.title = pr_payload.get("title") or ""
        pr.state = pr_payload.get("state") or "open"
        pr.base_ref = pr_payload["base"]["ref"]
        pr.base_sha = pr_payload["base"]["sha"]
        pr.head_ref = pr_payload["head"]["ref"]
        pr.head_sha = pr_payload["head"]["sha"]
        pr.html_url = pr_payload.get("html_url") or pr.html_url
        pr.merged = bool(pr_payload.get("merged"))
        await session.commit()
        logger.info("pull request upserted", extra={"pr_id": pr.id, "repo_id": repo.id})
        return pr.id


