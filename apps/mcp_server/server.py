"""Aura MCP server — real Model Context Protocol over stdio (or SSE).

Exposes the Aura analysis database to MCP-aware clients (Claude Code,
Cursor, Windsurf). Replaces the legacy HTTP stub.

Usage::

    python -m aura_mcp                  # stdio (default; for editors)
    python -m aura_mcp --transport sse  # browser/web demo
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from aura_backend.analysis.agents.embedding import QwenEmbedder

from . import _state
from .fts import ensure_fts


logger = logging.getLogger(__name__)


def _resolve_db_url() -> str:
    return os.getenv("AURA_DB_URL") or os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./aura.db")


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[None]:
    db_url = _resolve_db_url()
    engine = create_async_engine(db_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    _state.STATE.engine = engine
    _state.STATE.session_factory = session_factory
    _state.STATE.db_url = db_url

    # FTS5 setup is idempotent — safe to run on every start.
    try:
        await ensure_fts(engine)
    except Exception as exc:  # pragma: no cover - non-fatal
        logger.warning("fts setup failed", extra={"error": str(exc)})

    # Embedder is best-effort: if EMBEDDING_BASE_URL isn't set we skip
    # vector search and fall back to FTS-only.
    try:
        _state.STATE.embedder = QwenEmbedder()
    except Exception as exc:  # pragma: no cover
        logger.warning("embedder init failed", extra={"error": str(exc)})
        _state.STATE.embedder = None

    logger.info(
        "aura mcp server ready",
        extra={"db_url": db_url, "embedder_ready": _state.STATE.embedder is not None},
    )
    try:
        yield
    finally:
        with contextlib.suppress(Exception):
            await engine.dispose()


mcp = FastMCP(
    "aura",
    instructions=(
        "Aura is a living-documentation engine. Use these tools to answer "
        "questions about a codebase: prefer `search_docs` for free-form "
        "queries, `get_doc` for known doc paths, `get_symbol` for code "
        "details with verified line citations, `get_dependents` for blast "
        "radius, and `get_impact` for PR change summaries."
    ),
    lifespan=_lifespan,
)


# Tool registrations live in submodules to keep this file small.
# Importing them attaches @mcp.tool() decorators to ``mcp``.
from .tools import (  # noqa: E402, F401
    get_dependents,
    get_doc,
    get_impact,
    get_symbol,
    search_docs,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="aura-mcp")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse"),
        default=os.getenv("AURA_MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--port", type=int, default=int(os.getenv("AURA_MCP_PORT", "7338")))
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # FastMCP exposes its SSE app via .sse_app(); for hackathon scope
        # we just call .run("sse"). The default port is 8000; override by
        # setting MCP_PORT env if FastMCP version supports it.
        os.environ.setdefault("MCP_PORT", str(args.port))
        mcp.run(transport="sse")


if __name__ == "__main__":
    main()
