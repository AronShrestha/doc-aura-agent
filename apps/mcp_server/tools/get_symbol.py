"""Fetch a single symbol artifact with provenance + line citation data."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, func

from aura_backend.models import Artifact, ArtifactEdge

from ..server import mcp
from ._helpers import latest_run_id, session_factory


@mcp.tool()
async def get_symbol(repo_id: int, artifact_id: str) -> dict[str, Any]:
    """Return symbol metadata + dependent/dependency counts.

    Use this when you need verified-by-source line ranges to cite the
    original code (e.g. ``[verified: app/auth.py:L42-L58]``). Returns the
    full artifact payload including ``semantic_hash``, ``signature``,
    ``docstring``, ``decorators``, plus inbound/outbound edge counts.
    """
    factory = session_factory()
    async with factory() as session:
        run_id = await latest_run_id(session, repo_id)
        if run_id is None:
            return {"error": "no_runs_for_repo"}

        art = (
            await session.execute(
                select(Artifact).where(
                    Artifact.run_id == run_id, Artifact.artifact_id == artifact_id
                )
            )
        ).scalars().first()
        if art is None:
            return {"error": "artifact_not_found", "artifact_id": artifact_id}

        in_count = (
            await session.execute(
                select(func.count(ArtifactEdge.id)).where(
                    ArtifactEdge.run_id == run_id,
                    ArtifactEdge.dst_artifact_id == artifact_id,
                )
            )
        ).scalar_one()
        out_count = (
            await session.execute(
                select(func.count(ArtifactEdge.id)).where(
                    ArtifactEdge.run_id == run_id,
                    ArtifactEdge.src_artifact_id == artifact_id,
                )
            )
        ).scalar_one()

        return {
            "artifact_id": art.artifact_id,
            "category": art.category,
            "name": art.name,
            "source_file": art.source_file,
            "source_line_start": art.source_line_start,
            "source_line_end": art.source_line_end,
            "payload": art.payload,
            "verified_citation": (
                f"[verified: {art.source_file}:L{art.source_line_start}-L{art.source_line_end}]"
                if art.source_file and art.source_line_start and art.source_line_end
                else None
            ),
            "inbound_edges": int(in_count),
            "outbound_edges": int(out_count),
        }
