"""Shadow-PR generation — companion docs branch for every code PR.

Demo strategy: after ``pr_analysis.analyze_pull_request`` succeeds we
materialize the head run's ``GeneratedDoc`` rows into a local
``.aura/shadow_prs/pr-<pr_id>/`` tree and stamp the PR analysis row
with the synthetic URL + branch name. A real GitHub-pushing
implementation would re-use ``services/github`` to clone, branch,
commit, push, and open the companion PR; the local-write path is
sufficient for the hackathon demo (the UI shows the diff anyway).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..models import GeneratedDoc, PrAnalysisRun, PullRequest, Repo


logger = logging.getLogger(__name__)


def _shadow_root() -> Path:
    base = os.getenv("AURA_SHADOW_PR_DIR", ".aura/shadow_prs")
    return Path(base).resolve()


async def materialize_shadow_pr(
    session_factory: async_sessionmaker,
    pr_run_id: int,
) -> None:
    """Write the head-run docs to a parallel directory and update metadata."""
    async with session_factory() as session:
        pr_run = (
            await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.id == pr_run_id))
        ).scalars().first()
        if pr_run is None or pr_run.head_run_id is None:
            logger.warning("shadow pr skipped — no head run", extra={"pr_run_id": pr_run_id})
            return

        pr = (
            await session.execute(select(PullRequest).where(PullRequest.id == pr_run.pull_request_id))
        ).scalars().first()
        if pr is None:
            return
        repo = (await session.execute(select(Repo).where(Repo.id == pr.repo_id))).scalars().first()

        docs = (
            await session.execute(
                select(GeneratedDoc).where(GeneratedDoc.run_id == pr_run.head_run_id)
            )
        ).scalars().all()

        out_dir = _shadow_root() / f"pr-{pr.id}-{pr_run_id}"
        out_dir.mkdir(parents=True, exist_ok=True)
        for doc in docs:
            relpath = doc.slug_path.removeprefix(".aura/docs/")
            target = out_dir / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(doc.content_md, encoding="utf-8")

        branch = f"aura-docs/{pr.head_sha[:8]}" if pr.head_sha else f"aura-docs/pr-{pr.id}"
        full_name = repo.full_name if repo else "demo/repo"
        synthetic_url = f"https://github.com/{full_name}/pull/new/{branch}"

        pr_run.shadow_pr_branch = branch
        pr_run.shadow_pr_url = synthetic_url
        pr_run.shadow_pr_path = str(out_dir)
        pr_run.shadow_pr_file_count = len(docs)
        pr_run.updated_at = datetime.utcnow()
        await session.commit()

        logger.info(
            "shadow pr materialized",
            extra={
                "event": "shadow_pr_ready",
                "pr_run_id": pr_run_id,
                "branch": branch,
                "files": len(docs),
                "path": str(out_dir),
            },
        )
