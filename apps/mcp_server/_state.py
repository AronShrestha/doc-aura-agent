"""Process-wide MCP server state — engine, session factory, embedder.

Kept in a dedicated module so tools can import lightweight references
without triggering circular imports through ``server.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ServerState:
    engine: Any = None
    session_factory: Any = None
    embedder: Any = None
    db_url: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


STATE = ServerState()
