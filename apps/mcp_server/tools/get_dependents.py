"""BFS-based blast-radius lookup over the artifact graph."""

from __future__ import annotations

from collections import deque
from typing import Any

from sqlalchemy import select

from aura_backend.models import Artifact, ArtifactEdge

from ..server import mcp
from ._helpers import latest_run_id, session_factory


@mcp.tool()
async def get_dependents(
    repo_id: int,
    artifact_id: str,
    depth: int = 2,
    direction: str = "in",
) -> dict[str, Any]:
    """Return the blast radius of a symbol — who calls it (or whom it calls).

    Args:
        repo_id: repository ID
        artifact_id: starting node
        depth: BFS depth (1-5; default 2)
        direction: ``"in"`` for callers/predecessors, ``"out"`` for callees,
                   ``"both"`` for undirected.

    Returns ``{"layers": [[ids at depth=1], [ids at depth=2], ...]}``
    plus a ``nodes`` map with name + source_file for each id.
    """
    if depth < 1 or depth > 5:
        depth = 2
    factory = session_factory()
    async with factory() as session:
        run_id = await latest_run_id(session, repo_id)
        if run_id is None:
            return {"error": "no_runs_for_repo"}

        edges = (
            await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == run_id))
        ).scalars().all()
        forward: dict[str, list[str]] = {}
        backward: dict[str, list[str]] = {}
        for e in edges:
            forward.setdefault(e.src_artifact_id, []).append(e.dst_artifact_id)
            backward.setdefault(e.dst_artifact_id, []).append(e.src_artifact_id)

        if direction == "in":
            adj = backward
        elif direction == "out":
            adj = forward
        else:
            adj = {k: list({*forward.get(k, []), *backward.get(k, [])}) for k in {*forward, *backward}}

        layers: list[list[str]] = []
        seen: set[str] = {artifact_id}
        frontier: list[str] = [artifact_id]
        for _ in range(depth):
            nxt: list[str] = []
            for node in frontier:
                for neigh in adj.get(node, []):
                    if neigh in seen:
                        continue
                    seen.add(neigh)
                    nxt.append(neigh)
            if not nxt:
                break
            layers.append(nxt)
            frontier = nxt

        # Hydrate node metadata
        all_ids = {artifact_id} | {n for layer in layers for n in layer}
        nodes_rows = (
            await session.execute(
                select(Artifact).where(
                    Artifact.run_id == run_id, Artifact.artifact_id.in_(list(all_ids))
                )
            )
        ).scalars().all()
        nodes = {
            a.artifact_id: {
                "name": a.name,
                "category": a.category,
                "source_file": a.source_file,
                "line": a.source_line_start,
            }
            for a in nodes_rows
        }
        return {"start": artifact_id, "depth": depth, "direction": direction, "layers": layers, "nodes": nodes}
