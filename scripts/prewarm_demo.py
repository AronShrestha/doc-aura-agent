"""Prewarm Aura's analysis cache for a demo repository.

Runs ``run_static_analysis_for_ref`` on the *base* branch of a chosen
demo repo and persists the result so the live demo only needs to
generate head deltas. Pre-warming dramatically shortens the time from
"submit PR" → "see doc diff" on stage.

Usage::

    AURA_DB_URL=sqlite+aiosqlite:////tmp/aura.db \
    AURA_DEMO_REPO_PATH=/tmp/demo-repo \
    AURA_DEMO_REPO_ID=1 \
    AURA_DEMO_BRANCH=main \
    python scripts/prewarm_demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "backend"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from aura_backend.analysis.pipeline import run_static_analysis_for_ref
from aura_backend.models import Base


async def main() -> None:
    db_url = os.getenv("AURA_DB_URL", "sqlite+aiosqlite:///./aura.db")
    repo_id = int(os.getenv("AURA_DEMO_REPO_ID", "1"))
    branch = os.getenv("AURA_DEMO_BRANCH", "main")
    sha = os.getenv("AURA_DEMO_SHA", "")

    engine = create_async_engine(db_url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    print(f"prewarm: repo_id={repo_id} branch={branch} db={db_url}")
    run_id = await run_static_analysis_for_ref(session_factory, repo_id, branch, sha)
    print(f"prewarm: completed run_id={run_id}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
