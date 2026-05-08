"""Shared helpers for MCP tools."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aura_backend.models import AnalysisRun

from .._state import STATE


async def latest_run_id(session: AsyncSession, repo_id: int) -> int | None:
    row = (
        await session.execute(
            select(AnalysisRun)
            .where(AnalysisRun.repo_id == repo_id)
            .order_by(AnalysisRun.id.desc())
        )
    ).scalars().first()
    return row.id if row else None


def session_factory():
    """Return the bound async_sessionmaker (raises if lifespan didn't run)."""
    if STATE.session_factory is None:
        raise RuntimeError("mcp_server_not_initialized")
    return STATE.session_factory
