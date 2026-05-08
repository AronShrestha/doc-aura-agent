"""Per-language import-binding extraction (Aura MVP: Python + JS/TS only)."""

from __future__ import annotations

from collections.abc import Callable

from tree_sitter import Node

from ...models import NamedBinding
from .python import extract_python_bindings
from .ts_js import extract_ts_js_bindings


_DISPATCH: dict[str, Callable[[Node, str], tuple[list[str], list[NamedBinding]]]] = {
    "python": extract_python_bindings,
    "typescript": extract_ts_js_bindings,
    "javascript": extract_ts_js_bindings,
}


def extract_import_bindings(
    stmt_node: Node, src: str, lang: str
) -> tuple[list[str], list[NamedBinding]]:
    extractor = _DISPATCH.get(lang)
    if extractor is None:
        return [], []
    return extractor(stmt_node, src)


__all__ = [
    "extract_import_bindings",
    "extract_python_bindings",
    "extract_ts_js_bindings",
]
