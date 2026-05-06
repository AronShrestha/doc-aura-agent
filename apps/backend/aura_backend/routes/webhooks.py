from __future__ import annotations

import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import PullRequest, Repo
from ..services.github_app import build_app_jwt, create_installation_token
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
    if x_github_event != "pull_request":
        logger.info("github webhook ignored", extra={"event": "github_webhook_ignored"})
        return {"status": "ignored", "event": x_github_event}
    action = payload.get("action")
    if action not in {"opened", "synchronize", "reopened"}:
        logger.info("pull request webhook action ignored", extra={"event": "github_webhook_ignored"})
        return {"status": "ignored", "action": action}
    pr_id = await _upsert_pr(payload)
    logger.info("pull request webhook accepted", extra={"pr_id": pr_id, "event": "github_webhook_accepted"})
    await analyze_pull_request(SessionLocal, pr_id)
    await _post_or_update_comment(pr_id)
    return {"status": "accepted", "pull_request_id": pr_id}


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
        await session.commit()
        logger.info("pull request upserted", extra={"pr_id": pr.id, "repo_id": repo.id})
        return pr.id


async def _post_or_update_comment(pull_request_id: int) -> None:
    from sqlalchemy import select
    from ..models import GithubOAuthToken, PrAnalysisRun

    async with SessionLocal() as session:
        pr = (await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))).scalar_one()
        run = (await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.pull_request_id == pr.id).order_by(PrAnalysisRun.id.desc()))).scalars().first()
        repo = (await session.execute(select(Repo).where(Repo.id == pr.repo_id))).scalar_one()
        token_row = (await session.execute(select(GithubOAuthToken).order_by(GithubOAuthToken.id.desc()))).scalars().first()
        if not run or not run.review_comment_body:
            logger.info("skipping pr comment; no review body", extra={"pr_id": pull_request_id})
            return
        if repo.installation_id and repo.installation_id != "oauth":
            app_jwt = build_app_jwt(settings.github_app_id, settings.github_app_private_key)
            token = await create_installation_token(app_jwt, repo.installation_id)
        elif token_row:
            token = token_row.access_token
        else:
            logger.warning("skipping pr comment; no github token", extra={"pr_id": pull_request_id})
            return
        body = run.review_comment_body
        comments_url = f"https://api.github.com/repos/{repo.owner}/{repo.name}/issues/{pr.number}/comments"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        async with httpx.AsyncClient(timeout=20) as client:
            if pr.comment_id:
                resp = await client.patch(f"https://api.github.com/repos/{repo.owner}/{repo.name}/issues/comments/{pr.comment_id}", headers=headers, json={"body": body})
                if resp.status_code < 400:
                    logger.info("pr comment updated", extra={"pr_id": pull_request_id})
                    return
            resp = await client.post(comments_url, headers=headers, json={"body": body})
            if resp.status_code < 400:
                pr.comment_id = str(resp.json().get("id", ""))
                await session.commit()
                logger.info("pr comment posted", extra={"pr_id": pull_request_id})
            else:
                logger.warning("pr comment post failed", extra={"pr_id": pull_request_id})
