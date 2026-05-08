"""Fetch a single generated doc by slug path or artifact id."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from aura_backend.models import GeneratedDoc

from ..server import mcp
from ._helpers import latest_run_id, session_factory


@mcp.tool()
async def get_doc(repo_id: int, slug: str | None = None, artifact_id: str | None = None) -> dict[str, Any]:
    """Return the full Markdown for one generated doc.

    Provide either ``slug`` (e.g. ``.aura/docs/endpoints/get-users.md``)
    or ``artifact_id``. Slug match falls back to substring search if no
    exact match is found.
    """
    if not slug and not artifact_id:
        return {"error": "must_provide_slug_or_artifact_id"}

    factory = session_factory()
    async with factory() as session:
        run_id = await latest_run_id(session, repo_id)
        if run_id is None:
            return {"error": "no_runs_for_repo"}

        stmt = select(GeneratedDoc).where(GeneratedDoc.run_id == run_id)
        if artifact_id:
            stmt = stmt.where(GeneratedDoc.artifact_id == artifact_id)
        elif slug:
            # Try exact match first
            exact = (
                await session.execute(stmt.where(GeneratedDoc.slug_path == slug))
            ).scalars().first()
            if exact:
                return _serialize(exact)
            stmt = stmt.where(GeneratedDoc.slug_path.like(f"%{slug}%"))

        doc = (await session.execute(stmt.limit(1))).scalars().first()
        if doc is None:
            return {"error": "doc_not_found", "slug": slug, "artifact_id": artifact_id}
        return _serialize(doc)


def _serialize(doc: GeneratedDoc) -> dict[str, Any]:
    return {
        "artifact_id": doc.artifact_id,
        "slug_path": doc.slug_path,
        "title": doc.title,
        "category": doc.category,
        "content_md": doc.content_md,
        "content_hash": doc.content_hash,
        "source_files": doc.source_files,
        "source_lines": doc.source_lines,
    }
