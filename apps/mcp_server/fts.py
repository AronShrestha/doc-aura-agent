"""SQLite FTS5 setup + sync triggers for ``generated_docs``.

The MCP server's ``search_docs`` tool uses FTS5 as the lexical-search
arm of an RRF blend with vector cosine similarity. The schema is
created idempotently on startup so we do not need an Alembic migration
for the demo path.
"""

from __future__ import annotations

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


logger = logging.getLogger(__name__)


_SETUP_SQL = [
    # Self-contained FTS5 virtual table (rowid mirrors GeneratedDoc.id).
    # `tokenize='porter unicode61'` enables stemming + diacritic-folding so
    # queries like 'login' match 'logged in'. Self-contained (not
    # external-content) keeps trigger INSERTs simple.
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
        slug_path,
        title,
        content_md,
        tokenize = 'porter unicode61'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS generated_docs_ai
    AFTER INSERT ON generated_docs BEGIN
        INSERT INTO docs_fts(rowid, slug_path, title, content_md)
        VALUES (new.id, new.slug_path, new.title, new.content_md);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS generated_docs_ad
    AFTER DELETE ON generated_docs BEGIN
        DELETE FROM docs_fts WHERE rowid = old.id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS generated_docs_au
    AFTER UPDATE ON generated_docs BEGIN
        DELETE FROM docs_fts WHERE rowid = old.id;
        INSERT INTO docs_fts(rowid, slug_path, title, content_md)
        VALUES (new.id, new.slug_path, new.title, new.content_md);
    END
    """,
]


async def ensure_fts(engine: AsyncEngine) -> None:
    """Run idempotent FTS setup and backfill any orphan rows.

    Safe to call on every server start — uses ``IF NOT EXISTS`` and only
    re-indexes documents that aren't already in the virtual table.
    """
    async with engine.begin() as conn:
        for stmt in _SETUP_SQL:
            await conn.execute(text(stmt))

        # Backfill: copy any existing generated_docs rows into FTS that
        # weren't picked up by the AFTER INSERT trigger (e.g. legacy
        # rows present before triggers were installed).
        await conn.execute(
            text(
                """
                INSERT INTO docs_fts(rowid, slug_path, title, content_md)
                SELECT g.id, g.slug_path, g.title, g.content_md
                FROM generated_docs g
                LEFT JOIN docs_fts f ON f.rowid = g.id
                WHERE f.rowid IS NULL
                """
            )
        )
    logger.info("fts setup complete", extra={"event": "fts_ready"})
