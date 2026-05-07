from __future__ import annotations

import base64
import json
import logging
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..analysis.pipeline import docs_manifest_from_rows
from ..config import settings
from ..models import AnalysisRun, DocDiff, GeneratedDoc, GithubOAuthToken, PrAnalysisRun, PullRequest, Repo
from .github_app import build_app_jwt, create_installation_token


logger = logging.getLogger(__name__)

REVIEW_MARKER = "<!-- aura-pr-review -->"
DOCS_FOLLOWUP_MARKER = "<!-- aura-docs-followup -->"


async def post_or_update_review_comment(session_factory: async_sessionmaker, pull_request_id: int) -> None:
    async with session_factory() as session:
        pr = (await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))).scalar_one()
        run = (
            await session.execute(
                select(PrAnalysisRun).where(PrAnalysisRun.pull_request_id == pr.id).order_by(PrAnalysisRun.id.desc())
            )
        ).scalars().first()
        repo = (await session.execute(select(Repo).where(Repo.id == pr.repo_id))).scalar_one()
        if not run or not run.review_comment_body:
            logger.info("skipping pr review comment; no review body", extra={"pr_id": pull_request_id})
            return

        body = run.review_comment_body
        token = await repo_access_token(session_factory, repo)
        comment_id = pr.comment_id
        if not comment_id:
            comment_id = await _find_issue_comment_id_by_marker(token, repo, pr.number, REVIEW_MARKER)
        comment_id = await _create_or_update_issue_comment(token, repo, pr.number, body, comment_id)
        pr.comment_id = comment_id
        await session.commit()
        logger.info("pr review comment synced", extra={"pr_id": pull_request_id, "comment_id": comment_id})


async def create_or_update_docs_followup_pr(session_factory: async_sessionmaker, pull_request_id: int) -> dict[str, Any]:
    async with session_factory() as session:
        pr = (await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))).scalar_one()
        repo = (await session.execute(select(Repo).where(Repo.id == pr.repo_id))).scalar_one()
        pr_run = (
            await session.execute(
                select(PrAnalysisRun)
                .where(PrAnalysisRun.pull_request_id == pr.id, PrAnalysisRun.status == "succeeded")
                .order_by(PrAnalysisRun.id.desc())
            )
        ).scalars().first()
        if not pr_run:
            raise RuntimeError("pr_analysis_not_ready")

        diffs = (
            await session.execute(select(DocDiff).where(DocDiff.pr_analysis_run_id == pr_run.id).order_by(DocDiff.doc_path))
        ).scalars().all()
        if not diffs:
            return {
                "status": "noop",
                "message": "No documentation changes required for this PR.",
                "pull_request_id": pull_request_id,
            }

        head_run = None
        if pr_run.head_run_id:
            head_run = (await session.execute(select(AnalysisRun).where(AnalysisRun.id == pr_run.head_run_id))).scalar_one()
        if not head_run:
            raise RuntimeError("pr_head_analysis_missing")

        base_docs = []
        if pr_run.base_run_id:
            base_docs = (
                await session.execute(select(GeneratedDoc).where(GeneratedDoc.run_id == pr_run.base_run_id))
            ).scalars().all()
        head_docs = (
            await session.execute(select(GeneratedDoc).where(GeneratedDoc.run_id == pr_run.head_run_id))
        ).scalars().all()

    token = await repo_access_token(session_factory, repo)
    branch_name = _docs_branch_name(pr)
    base_branch_sha = await _branch_head_sha(token, repo, pr.base_ref)
    await _ensure_branch(token, repo, branch_name, base_branch_sha)

    publish_result = await _publish_docs_snapshot(
        token=token,
        repo=repo,
        branch_name=branch_name,
        pr=pr,
        base_docs=base_docs,
        head_docs=head_docs,
        repo_sha=head_run.commit_sha or head_run.branch or pr.head_sha,
    )

    if not publish_result["changed_paths"] and not publish_result["removed_paths"]:
        existing = await _find_open_pull_request(token, repo, branch_name, pr.base_ref)
        if existing:
            pr_payload = existing
        else:
            pr_payload = await _create_or_update_pull_request(
                token=token,
                repo=repo,
                branch_name=branch_name,
                base_ref=pr.base_ref,
                title=_docs_pr_title(pr),
                body=_docs_pr_body(pr, pr_run, diffs),
            )
    else:
        pr_payload = await _create_or_update_pull_request(
            token=token,
            repo=repo,
            branch_name=branch_name,
            base_ref=pr.base_ref,
            title=_docs_pr_title(pr),
            body=_docs_pr_body(pr, pr_run, diffs),
        )

    await upsert_pr_marker_comment(
        session_factory,
        pull_request_id,
        DOCS_FOLLOWUP_MARKER,
        _docs_followup_comment_body(pr, pr_payload),
    )

    logger.info(
        "docs follow-up pr synced",
        extra={"pr_id": pull_request_id, "docs_pr_number": pr_payload["number"], "branch": branch_name},
    )
    return {
        "status": "ready",
        "pull_request_id": pull_request_id,
        "docs_branch": branch_name,
        "docs_pull_request": {
            "number": pr_payload["number"],
            "url": pr_payload["html_url"],
            "title": pr_payload["title"],
        },
        "changed_paths": publish_result["changed_paths"],
        "removed_paths": publish_result["removed_paths"],
    }


async def upsert_pr_marker_comment(
    session_factory: async_sessionmaker,
    pull_request_id: int,
    marker: str,
    body: str,
) -> str:
    async with session_factory() as session:
        pr = (await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))).scalar_one()
        repo = (await session.execute(select(Repo).where(Repo.id == pr.repo_id))).scalar_one()

    token = await repo_access_token(session_factory, repo)
    comment_id = await _find_issue_comment_id_by_marker(token, repo, pr.number, marker)
    return await _create_or_update_issue_comment(token, repo, pr.number, body, comment_id)


async def repo_access_token(session_factory: async_sessionmaker, repo: Repo) -> str:
    if repo.installation_id and repo.installation_id != "oauth":
        app_jwt = build_app_jwt(settings.github_app_id, settings.github_app_private_key)
        return await create_installation_token(app_jwt, repo.installation_id)

    async with session_factory() as session:
        token_row = (await session.execute(select(GithubOAuthToken).order_by(GithubOAuthToken.id.desc()))).scalars().first()

    if token_row is None:
        raise RuntimeError("github_token_missing")

    return token_row.access_token


async def _publish_docs_snapshot(
    *,
    token: str,
    repo: Repo,
    branch_name: str,
    pr: PullRequest,
    base_docs: list[GeneratedDoc],
    head_docs: list[GeneratedDoc],
    repo_sha: str,
) -> dict[str, list[str]]:
    manifest = docs_manifest_from_rows(head_docs)
    manifest["repo_id"] = repo.id
    manifest["repo_sha"] = repo_sha

    target_files = {doc.slug_path: doc.content_md for doc in head_docs}
    target_files[".aura/docs/.aura-manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    changed_paths: list[str] = []
    for path, content in sorted(target_files.items()):
        changed = await _upsert_file_contents(
            token,
            repo,
            branch_name,
            path,
            content,
            f"docs: refresh Aura docs for PR #{pr.number}",
        )
        if changed:
            changed_paths.append(path)

    head_paths = set(target_files)
    removable_paths = {doc.slug_path for doc in base_docs} | {".aura/docs/.aura-manifest.json"}
    removed_paths: list[str] = []
    for path in sorted(removable_paths - head_paths):
        removed = await _delete_file_if_present(
            token,
            repo,
            branch_name,
            path,
            f"docs: remove stale Aura docs for PR #{pr.number}",
        )
        if removed:
            removed_paths.append(path)

    return {"changed_paths": changed_paths, "removed_paths": removed_paths}


async def _upsert_file_contents(
    token: str,
    repo: Repo,
    branch_name: str,
    path: str,
    content: str,
    message: str,
) -> bool:
    existing = await _get_file_content(token, repo, branch_name, path)
    if existing and existing["content"] == content:
        return False

    payload: dict[str, Any] = {
        "message": message,
        "branch": branch_name,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    if existing and existing["sha"]:
        payload["sha"] = existing["sha"]

    await _github_request(
        "PUT",
        f"https://api.github.com/repos/{repo.owner}/{repo.name}/contents/{_quote_repo_path(path)}",
        token,
        json=payload,
    )
    return True


async def _delete_file_if_present(
    token: str,
    repo: Repo,
    branch_name: str,
    path: str,
    message: str,
) -> bool:
    existing = await _get_file_content(token, repo, branch_name, path)
    if not existing or not existing["sha"]:
        return False

    await _github_request(
        "DELETE",
        f"https://api.github.com/repos/{repo.owner}/{repo.name}/contents/{_quote_repo_path(path)}",
        token,
        json={
            "message": message,
            "branch": branch_name,
            "sha": existing["sha"],
        },
    )
    return True


async def _get_file_content(token: str, repo: Repo, branch_name: str, path: str) -> dict[str, str] | None:
    resp = await _github_request(
        "GET",
        f"https://api.github.com/repos/{repo.owner}/{repo.name}/contents/{_quote_repo_path(path)}",
        token,
        params={"ref": branch_name},
        allow_404=True,
    )
    if resp is None:
        return None

    payload = resp.json()
    encoded = (payload.get("content") or "").replace("\n", "")
    decoded = base64.b64decode(encoded).decode("utf-8") if encoded else ""
    return {"sha": payload.get("sha", ""), "content": decoded}


async def _branch_head_sha(token: str, repo: Repo, branch_name: str) -> str:
    resp = await _github_request(
        "GET",
        f"https://api.github.com/repos/{repo.owner}/{repo.name}/git/ref/heads/{branch_name}",
        token,
    )
    return resp.json()["object"]["sha"]


async def _ensure_branch(token: str, repo: Repo, branch_name: str, base_sha: str) -> None:
    existing = await _github_request(
        "GET",
        f"https://api.github.com/repos/{repo.owner}/{repo.name}/git/ref/heads/{branch_name}",
        token,
        allow_404=True,
    )
    if existing is not None:
        return

    await _github_request(
        "POST",
        f"https://api.github.com/repos/{repo.owner}/{repo.name}/git/refs",
        token,
        json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
    )


async def _create_or_update_pull_request(
    *,
    token: str,
    repo: Repo,
    branch_name: str,
    base_ref: str,
    title: str,
    body: str,
) -> dict[str, Any]:
    existing = await _find_open_pull_request(token, repo, branch_name, base_ref)
    if existing:
        pr_number = existing["number"]
        resp = await _github_request(
            "PATCH",
            f"https://api.github.com/repos/{repo.owner}/{repo.name}/pulls/{pr_number}",
            token,
            json={"title": title, "body": body},
        )
        return resp.json()

    resp = await _github_request(
        "POST",
        f"https://api.github.com/repos/{repo.owner}/{repo.name}/pulls",
        token,
        json={"title": title, "body": body, "head": branch_name, "base": base_ref},
    )
    return resp.json()


async def _find_open_pull_request(token: str, repo: Repo, branch_name: str, base_ref: str) -> dict[str, Any] | None:
    resp = await _github_request(
        "GET",
        f"https://api.github.com/repos/{repo.owner}/{repo.name}/pulls",
        token,
        params={"state": "open", "head": f"{repo.owner}:{branch_name}", "base": base_ref},
    )
    pulls = resp.json()
    return pulls[0] if pulls else None


async def _create_or_update_issue_comment(
    token: str,
    repo: Repo,
    pr_number: int,
    body: str,
    comment_id: str | None,
) -> str:
    if comment_id:
        resp = await _github_request(
            "PATCH",
            f"https://api.github.com/repos/{repo.owner}/{repo.name}/issues/comments/{comment_id}",
            token,
            json={"body": body},
            allow_404=True,
        )
        if resp is not None and resp.status_code < 400:
            return str(resp.json().get("id", comment_id))

    resp = await _github_request(
        "POST",
        f"https://api.github.com/repos/{repo.owner}/{repo.name}/issues/{pr_number}/comments",
        token,
        json={"body": body},
    )
    return str(resp.json().get("id", ""))


async def _find_issue_comment_id_by_marker(token: str, repo: Repo, pr_number: int, marker: str) -> str | None:
    resp = await _github_request(
        "GET",
        f"https://api.github.com/repos/{repo.owner}/{repo.name}/issues/{pr_number}/comments",
        token,
        params={"per_page": 100},
    )
    for comment in resp.json():
        if marker in str(comment.get("body") or ""):
            return str(comment.get("id", ""))
    return None


async def _github_request(
    method: str,
    url: str,
    token: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    allow_404: bool = False,
) -> httpx.Response | None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, headers=headers, json=json, params=params)

    if allow_404 and resp.status_code == 404:
        return None

    if resp.status_code >= 400:
        raise RuntimeError(f"github_api_failed:{resp.status_code}:{method}:{url}:{resp.text[:500]}")

    return resp


def _docs_branch_name(pr: PullRequest) -> str:
    head = (pr.head_sha or pr.head_ref or "head").replace("/", "-")
    return f"aura/docs/pr-{pr.number}-{head[:12]}"


def _docs_pr_title(pr: PullRequest) -> str:
    return f"docs: refresh Aura docs for PR #{pr.number}"


def _docs_pr_body(pr: PullRequest, pr_run: PrAnalysisRun, diffs: list[DocDiff]) -> str:
    impact = pr_run.impact_summary or {}
    severity = impact.get("severity_counts") or {}
    changed_paths = sorted({diff.doc_path for diff in diffs})
    head_sha = (pr.head_sha or "")[:12] or "unknown"
    lines = [
        "## Aura Documentation Follow-up",
        "",
        f"- Source PR: #{pr.number} - {pr.title}",
        f"- Base branch: `{pr.base_ref}`",
        f"- Source head: `{pr.head_ref}` @ `{head_sha}`",
        f"- Documentation changes generated: {len(changed_paths)}",
        f"- Critical impacts: {severity.get('critical', 0)}",
        f"- Warning impacts: {severity.get('warning', 0)}",
        "",
        "Merge this after the source PR lands or in coordination with it.",
        "",
        "### Generated Doc Paths",
    ]
    lines.extend(f"- `{path}`" for path in changed_paths[:20])
    if len(changed_paths) > 20:
        lines.append(f"- ...and {len(changed_paths) - 20} more")
    return "\n".join(lines)


def _docs_followup_comment_body(pr: PullRequest, docs_pr_payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            DOCS_FOLLOWUP_MARKER,
            "## Aura Documentation Follow-up",
            "",
            f"A companion documentation PR is ready for source PR #{pr.number}.",
            "",
            f"- Docs PR: #{docs_pr_payload['number']} - {docs_pr_payload['html_url']}",
            f"- Branch: `{docs_pr_payload['head']['ref']}`",
            "",
            "Merge the docs PR after the source PR is approved and landed.",
        ]
    )


def _quote_repo_path(path: str) -> str:
    return quote(path, safe="/")
