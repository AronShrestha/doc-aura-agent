from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import PullRequest, Repo
from ..services.post_merge import enqueue_canonical_analysis
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
        merge_commit_sha = pr_payload.get("merge_commit_sha") or pr_payload.get("head", {}).get("sha", "")
        result = await _promote_on_merge(pr_id, merge_commit_sha=merge_commit_sha)
        logger.info(
            "pull request merged; canonical refresh dispatched",
            extra={"pr_id": pr_id, "event": "pr_merged", **result},
        )
        return {"status": "merged", "pull_request_id": pr_id, **result}

    if action == "closed" and not pr_payload.get("merged"):
        pr_id = await _upsert_pr(payload)
        logger.info(
            "pull request closed without merge; no doc refresh",
            extra={"event": "github_webhook_closed_unmerged", "pr_id": pr_id},
        )
        return {"status": "closed_unmerged", "pull_request_id": pr_id}

    if action not in {"opened", "synchronize", "reopened"}:
        logger.info("pull request webhook action ignored", extra={"event": "github_webhook_ignored", "action": action})
        return {"status": "ignored", "action": action}

    pr_id = await _upsert_pr(payload)
    logger.info("pull request webhook accepted", extra={"pr_id": pr_id, "event": "github_webhook_accepted"})
    await run_pr_orchestrator(SessionLocal, pr_id)
    return {"status": "accepted", "pull_request_id": pr_id}


async def _promote_on_merge(
    pull_request_id: int,
    *,
    merge_commit_sha: str = "",
) -> dict:
    """On PR merge into the default branch:

    1. **Layer A (instant preview)** — copy LLM-edited doc snippets cached in
       ``DocDiff`` rows into the canonical ``GeneratedDoc.content_md`` so the
       UI reflects the merge immediately. Refresh embeddings on every patched
       doc so the docs-chat retriever doesn't keep returning stale text. New
       docs introduced by the PR (no canonical row yet) get inserted instead
       of silently dropped.
    2. **Layer B (source of truth)** — enqueue a fresh canonical
       ``AnalysisRun`` on the merge commit. That re-extracts artifacts,
       regenerates docs, recomputes graph edges, and re-embeds everything —
       reconciling new files / removed code / new artifacts that the snippet
       patch can't see.

    Returns a small dict surfaced through the webhook response so the result
    is observable in CI / GitHub redelivery logs:

        {
            "promoted_run_id": <canonical run id or None>,
            "applied": <docs whose content_md was patched>,
            "created_docs": <docs newly inserted into canonical>,
            "embedded": <docs whose embedding was refreshed>,
            "fresh_run_id": <newly enqueued canonical run id or None>,
            "skip_reason": <"no_pr" | "no_pr_run" | "no_canonical" | None>,
        }
    """
    import hashlib

    from ..analysis.agents.embedding import QwenEmbedder, pack_vector
    from ..models import AnalysisRun, DocDiff, GeneratedDoc, PrAnalysisRun, PullRequest

    result: dict = {
        "promoted_run_id": None,
        "applied": 0,
        "created_docs": 0,
        "embedded": 0,
        "fresh_run_id": None,
        "skip_reason": None,
    }
    repo_id_for_enqueue: int | None = None

    async with SessionLocal() as session:
        pr = (
            await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))
        ).scalar_one_or_none()
        if not pr:
            logger.warning(
                "merge: pull request row missing; skipping",
                extra={"event": "merge_skip", "pr_id": pull_request_id, "reason": "no_pr"},
            )
            result["skip_reason"] = "no_pr"
            return result
        repo_id_for_enqueue = pr.repo_id
        pr_run = (
            await session.execute(
                select(PrAnalysisRun)
                .where(PrAnalysisRun.pull_request_id == pull_request_id)
                .order_by(PrAnalysisRun.id.desc())
            )
        ).scalars().first()
        if not pr_run:
            logger.info(
                "merge: no PrAnalysisRun for PR; nothing to promote",
                extra={"event": "merge_skip", "pr_id": pull_request_id, "reason": "no_pr_run"},
            )
            result["skip_reason"] = "no_pr_run"
        else:
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
                logger.warning(
                    "merge: no canonical run; will only enqueue fresh analysis",
                    extra={"event": "merge_skip", "pr_id": pull_request_id, "reason": "no_canonical"},
                )
                result["skip_reason"] = "no_canonical"
            else:
                result["promoted_run_id"] = canonical.id
                diffs = (
                    await session.execute(
                        select(DocDiff).where(DocDiff.pr_analysis_run_id == pr_run.id)
                    )
                ).scalars().all()
                canonical_docs = (
                    await session.execute(
                        select(GeneratedDoc).where(GeneratedDoc.run_id == canonical.id)
                    )
                ).scalars().all()
                canonical_by_aid = {d.artifact_id: d for d in canonical_docs}
                changed_docs: list[GeneratedDoc] = []

                for diff in diffs:
                    after_text = _extract_head_text(diff.side_by_side)
                    if not after_text:
                        continue
                    doc = canonical_by_aid.get(diff.artifact_id)
                    if doc is None:
                        # Brand-new doc introduced by the PR. Insert into the
                        # canonical run so the UI sees it immediately. The
                        # follow-up fresh run will replace this with the
                        # full, properly-categorised output of the
                        # canonical pipeline.
                        title = _title_from_doc_diff(diff, after_text)
                        doc = GeneratedDoc(
                            run_id=canonical.id,
                            artifact_id=diff.artifact_id,
                            category="updated",
                            title=title,
                            slug_path=diff.doc_path or f".aura/docs/{diff.artifact_id}.md",
                            content_hash=hashlib.sha256(after_text.encode("utf-8")).hexdigest(),
                            generated_sha=merge_commit_sha or "",
                            last_verified_sha="",
                            source_files=[],
                            source_lines={},
                            content_md=after_text,
                        )
                        session.add(doc)
                        canonical_by_aid[diff.artifact_id] = doc
                        changed_docs.append(doc)
                        result["created_docs"] += 1
                        continue
                    if after_text == (doc.content_md or ""):
                        continue
                    doc.content_md = after_text
                    doc.content_hash = hashlib.sha256(after_text.encode("utf-8")).hexdigest()
                    changed_docs.append(doc)
                    result["applied"] += 1

                if changed_docs:
                    try:
                        embedder = QwenEmbedder()
                        embed_result = await embedder.embed([d.content_md or "" for d in changed_docs])
                        for d, vec in zip(changed_docs, embed_result.vectors):
                            d.embedding = pack_vector(vec)
                            d.embedding_dim = embed_result.dim
                            d.embedding_model = embed_result.model
                            result["embedded"] += 1
                    except Exception:
                        # Embedding refresh is best-effort. The follow-up
                        # canonical run will recompute these correctly.
                        logger.exception(
                            "merge: embedding refresh failed (fresh run will fix)",
                            extra={"event": "merge_embed_error", "pr_id": pull_request_id},
                        )
                    await session.commit()

                logger.info(
                    "merge: docs promoted",
                    extra={
                        "event": "merge_promoted",
                        "pr_id": pull_request_id,
                        "canonical_run_id": canonical.id,
                        "applied": result["applied"],
                        "created_docs": result["created_docs"],
                        "embedded": result["embedded"],
                    },
                )

    if repo_id_for_enqueue is not None:
        try:
            fresh_id = await enqueue_canonical_analysis(
                repo_id=repo_id_for_enqueue, commit_sha=merge_commit_sha
            )
            result["fresh_run_id"] = fresh_id
        except Exception:
            logger.exception(
                "merge: failed to enqueue fresh canonical analysis",
                extra={"event": "merge_enqueue_error", "pr_id": pull_request_id},
            )

    return result


def _title_from_doc_diff(diff, after_text: str) -> str:
    """Best-effort title for a doc that didn't exist canonically yet.
    Looks for a leading Markdown H1, falls back to the slug stem.
    """
    for line in (after_text or "").splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip() or diff.artifact_id
    if diff.doc_path:
        stem = diff.doc_path.rsplit("/", 1)[-1]
        return stem.removesuffix(".md") or diff.artifact_id
    return diff.artifact_id


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


