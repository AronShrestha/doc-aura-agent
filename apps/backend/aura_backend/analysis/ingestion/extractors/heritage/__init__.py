"""Per-language heritage extraction (Aura MVP: Python + JS/TS only)."""

from __future__ import annotations

from collections.abc import Callable

from ...languages.registry import REGISTRY as _LANG_REGISTRY
from ...models import HeritageRelation
from ..helpers import node_text
from .python import _extract_python_heritage
from .ts_js import _extract_ts_js_heritage


def heritage_node_types_for(lang: str) -> frozenset[str]:
    spec = _LANG_REGISTRY.get(lang)
    return spec.heritage_node_types if spec else frozenset()


def _builtin_parents(lang: str) -> frozenset[str]:
    spec = _LANG_REGISTRY.get(lang)
    return spec.builtin_parents if spec else frozenset()


HERITAGE_EXTRACTORS: dict[str, Callable[..., None]] = {
    "python": _extract_python_heritage,
    "typescript": _extract_ts_js_heritage,
    "javascript": _extract_ts_js_heritage,
}


def extract_heritage(
    tree: object,
    query: object,
    config: object,
    file_info: object,
    src: str,
    *,
    run_query: Callable,
) -> list[HeritageRelation]:
    if query is None:
        return []

    lang = file_info.language  # type: ignore[attr-defined]
    heritage_types = heritage_node_types_for(lang)
    if not heritage_types:
        return []

    parent_builtins = _builtin_parents(lang)

    relations: list[HeritageRelation] = []
    seen: set[tuple[int, str]] = set()

    for capture_dict in run_query(query, tree.root_node):  # type: ignore[attr-defined]
        def_nodes = capture_dict.get("symbol.def", [])
        name_nodes = capture_dict.get("symbol.name", [])

        if not def_nodes or not name_nodes:
            continue

        def_node = def_nodes[0]
        if def_node.type not in heritage_types:
            continue

        name = node_text(name_nodes[0], src)
        if not name:
            continue

        line = def_node.start_point[0] + 1
        dedup_key = (line, name)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        extractor = HERITAGE_EXTRACTORS.get(lang)
        if extractor:
            extractor(def_node, name, line, src, relations)

    if parent_builtins:
        relations = [r for r in relations if r.parent_name not in parent_builtins]

    return relations


__all__ = ["HERITAGE_EXTRACTORS", "extract_heritage", "heritage_node_types_for"]
