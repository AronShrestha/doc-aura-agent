"""MCP tool modules — importing each registers an @mcp.tool() callback."""

from . import get_dependents, get_doc, get_impact, get_symbol, search_docs  # noqa: F401

__all__ = ["get_dependents", "get_doc", "get_impact", "get_symbol", "search_docs"]
