from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import PullRequest, Repo
from ..services.github_prs import create_or_update_docs_followup_pr, post_or_update_review_comment
from ..services.pr_analysis import analyze_pull_request

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
    action = payload.get("action")

    if x_github_event == "pull_request":
        if action not in {"opened", "synchronize", "reopened"}:
            logger.info("pull request webhook action ignored", extra={"event": "github_webhook_ignored"})
            return {"status": "ignored", "action": action}
        pr_id = await _upsert_pr(payload)
        logger.info("pull request webhook accepted", extra={"pr_id": pr_id, "event": "github_webhook_accepted"})
        await analyze_pull_request(SessionLocal, pr_id)
        await post_or_update_review_comment(SessionLocal, pr_id)
        return {"status": "accepted", "pull_request_id": pr_id}

    if x_github_event == "pull_request_review":
        review = payload.get("review") or {}
        if action != "submitted" or (review.get("state") or "").lower() != "approved":
            logger.info("pull request review webhook ignored", extra={"event": "github_webhook_ignored"})
            return {"status": "ignored", "action": action}
        pr_id = await _upsert_pr(payload)
        docs_result = await create_or_update_docs_followup_pr(SessionLocal, pr_id)
        return {"status": "accepted", "pull_request_id": pr_id, "docs_followup": docs_result}

    if x_github_event == "issue_comment":
        issue = payload.get("issue") or {}
        comment = payload.get("comment") or {}
        body_text = str(comment.get("body") or "").lower()
        if action not in {"created", "edited"} or not issue.get("pull_request"):
            logger.info("issue comment webhook ignored", extra={"event": "github_webhook_ignored"})
            return {"status": "ignored", "action": action}
        if "/aura docs" not in body_text and "/aura confirm-docs" not in body_text:
            logger.info("issue comment command ignored", extra={"event": "github_webhook_ignored"})
            return {"status": "ignored", "action": action}
        pr_id = await _upsert_pr(payload)
        docs_result = await create_or_update_docs_followup_pr(SessionLocal, pr_id)
        return {"status": "accepted", "pull_request_id": pr_id, "docs_followup": docs_result}

    logger.info("github webhook ignored", extra={"event": "github_webhook_ignored"})
    return {"status": "ignored", "event": x_github_event}


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
    pr_payload = payload.get("pull_request") or payload.get("issue") or {}
    installation_id = str((payload.get("installation") or {}).get("id") or "oauth")
    async with SessionLocal() as session:
        repo = (await session.execute(select(Repo).where(Repo.github_repo_id == str(repo_payload["id"])))).scalar_one_or_none()
        if not repo:
            repo = Repo(
                github_repo_id=str(repo_payload["id"]),
                full_name=repo_payload["full_name"],
                default_branch=repo_payload.get("default_branch", "main"),
                installation_id=installation_id,
                owner=repo_payload["owner"]["login"],
                name=repo_payload["name"],
            )
            session.add(repo)
            await session.flush()
        else:
            repo.full_name = repo_payload["full_name"]
            repo.default_branch = repo_payload.get("default_branch", repo.default_branch or "main")
            repo.installation_id = installation_id
            repo.owner = repo_payload["owner"]["login"]
            repo.name = repo_payload["name"]
        pr = (await session.execute(select(PullRequest).where(PullRequest.repo_id == repo.id, PullRequest.number == int(pr_payload["number"])))).scalar_one_or_none()
        if not pr:
            pr = PullRequest(repo_id=repo.id, github_pr_id=str(pr_payload.get("id", pr_payload["number"])), number=int(pr_payload["number"]))
            session.add(pr)
        pr.github_pr_id = str(pr_payload.get("id", pr.github_pr_id or pr_payload["number"]))
        pr.title = pr_payload.get("title") or pr.title or ""
        pr.state = pr_payload.get("state") or pr.state or "open"
        if pr_payload.get("base"):
            pr.base_ref = pr_payload["base"]["ref"]
            pr.base_sha = pr_payload["base"]["sha"]
        if pr_payload.get("head"):
            pr.head_ref = pr_payload["head"]["ref"]
            pr.head_sha = pr_payload["head"]["sha"]
        pr.updated_at = datetime.utcnow()
        await session.commit()
        logger.info("pull request upserted", extra={"pr_id": pr.id, "repo_id": repo.id})
        return pr.id
