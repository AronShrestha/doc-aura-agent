"""Post-merge orchestration: enqueue a fresh canonical AnalysisRun on the
merge commit so the artifact graph, doc set, and embeddings reconcile to the
new state of the default branch.

Mirrors the row shape produced by ``POST /repos/{repo_id}/re-analyze`` in
``routes/analysis.py`` (search for ``repo_re_analyze``) — keeping a single
canonical-run schema across user-triggered and webhook-triggered paths.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from ..db import SessionLocal
from ..models import AnalysisRun, Repo


logger = logging.getLogger(__name__)


async def enqueue_canonical_analysis(repo_id: int, commit_sha: str = "") -> int | None:
    """Create a new ``queued`` AnalysisRun on the repo's default branch and
    push it onto the in-process analysis queue. Returns the run id, or
    ``None`` if the repo cannot be found.

    Safe to call from a webhook handler — does not block on the analysis
    itself; the queue runs it in the background.
    """
    async with SessionLocal() as session:
        repo = (await session.execute(select(Repo).where(Repo.id == repo_id))).scalar_one_or_none()
        if not repo:
            logger.warning(
                "post_merge enqueue: repo not found",
                extra={"event": "post_merge_enqueue_skip", "repo_id": repo_id, "reason": "no_repo"},
            )
            return None
        # Inherit ownership from the repo. Without ``user_id`` the canonical
        # run row exists but ``GET /runs/{id}`` (which filters on user_id)
        # 404s for the repo's owner — the frontend then can't resolve
        # ``repo_id`` and the docs sidebar renders empty after merge.
        run = AnalysisRun(
            repo_id=repo.id,
            user_id=repo.user_id,
            status="queued",
            stage="queued",
            progress=0,
            branch=repo.default_branch,
            commit_sha=commit_sha or "",
            is_pr_run=False,
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    # Lazy import — avoids a circular import between main.py (which builds
    # the queue using SessionLocal) and this helper (imported via the
    # webhooks module which is wired into the FastAPI app at startup).
    from ..main import app_state

    await app_state.queue.start()
    await app_state.queue.enqueue(run_id)
    logger.info(
        "post_merge canonical analysis enqueued",
        extra={
            "event": "post_merge_enqueue",
            "repo_id": repo_id,
            "run_id": run_id,
            "commit_sha": commit_sha or None,
            "branch": repo.default_branch,
        },
    )
    return run_id
