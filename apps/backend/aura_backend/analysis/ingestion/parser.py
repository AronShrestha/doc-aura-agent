"""Unified AST parser — Python + JS/TS for Aura MVP.

Lifted + trimmed from repowise (AGPL-3.0). Uses ``tree-sitter-language-pack``
for grammar loading instead of repowise's dynamic ``__import__`` (avoids
needing individual ``tree_sitter_python`` etc. packages).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from tree_sitter import Language, Node, Parser
from tree_sitter_language_pack import get_language as _pack_get_language

from .extractors import (
    build_signature,
    extract_heritage,
    extract_import_bindings,
    extract_module_docstring,
    extract_symbol_docstring,
    node_text,
)
from .extractors.visibility import (
    public_by_default,
    py_visibility,
    ts_visibility,
)
from .languages.registry import REGISTRY as _LANG_REGISTRY
from .models import (
    CallSite,
    FileInfo,
    Import,
    ParsedFile,
    Symbol,
)

log = structlog.get_logger(__name__)

QUERIES_DIR = Path(__file__).parent / "queries"

_node_text = node_text


# ---------------------------------------------------------------------------
# Language registry — tag → tree-sitter Language object
# ---------------------------------------------------------------------------


def _build_language_registry() -> dict[str, Language]:
    """Lazily load tree-sitter language objects via tree-sitter-language-pack."""
    registry: dict[str, Language] = {}
    for tag in ("python", "javascript", "typescript"):
        try:
            registry[tag] = _pack_get_language(tag)
        except Exception as exc:
            log.debug("tree-sitter language unavailable", language=tag, reason=str(exc))
    # tsx variant
    try:
        registry["tsx"] = _pack_get_language("tsx")
    except Exception as exc:
        log.debug("tree-sitter language unavailable", language="tsx", reason=str(exc))
    return registry


_LANGUAGE_REGISTRY: dict[str, Language] = {}


def _get_language(tag: str) -> Language | None:
    global _LANGUAGE_REGISTRY
    if not _LANGUAGE_REGISTRY:
        _LANGUAGE_REGISTRY = _build_language_registry()
    return _LANGUAGE_REGISTRY.get(tag)


# ---------------------------------------------------------------------------
# LanguageConfig
# ---------------------------------------------------------------------------


@dataclass
class LanguageConfig:
    symbol_node_types: dict[str, str]
    import_node_types: list[str]
    export_node_types: list[str]
    visibility_fn: Callable[[str, list[str]], str]
    parent_extraction: str = "nesting"
    parent_class_types: frozenset[str] = field(default_factory=frozenset)
    entry_point_patterns: list[str] = field(default_factory=list)


LANGUAGE_CONFIGS: dict[str, LanguageConfig] = {
    "python": LanguageConfig(
        symbol_node_types={
            "function_definition": "function",
            "class_definition": "class",
        },
        import_node_types=["import_statement", "import_from_statement"],
        export_node_types=[],
        visibility_fn=py_visibility,
        parent_extraction="nesting",
        parent_class_types=frozenset({"class_definition"}),
        entry_point_patterns=["main.py", "app.py", "__main__.py", "manage.py", "wsgi.py"],
    ),
    "typescript": LanguageConfig(
        symbol_node_types={
            "function_declaration": "function",
            "generator_function_declaration": "function",
            "arrow_function": "function",
            "class_declaration": "class",
            "abstract_class_declaration": "class",
            "interface_declaration": "interface",
            "type_alias_declaration": "type_alias",
            "enum_declaration": "enum",
            "method_definition": "method",
            "lexical_declaration": "function",
        },
        import_node_types=["import_statement"],
        export_node_types=["export_statement"],
        visibility_fn=ts_visibility,
        parent_extraction="nesting",
        parent_class_types=frozenset({"class_declaration", "abstract_class_declaration"}),
        entry_point_patterns=["index.ts", "main.ts", "app.ts", "server.ts"],
    ),
    "javascript": LanguageConfig(
        symbol_node_types={
            "function_declaration": "function",
            "generator_function_declaration": "function",
            "arrow_function": "function",
            "class_declaration": "class",
            "method_definition": "method",
            "lexical_declaration": "function",
        },
        import_node_types=["import_statement"],
        export_node_types=["export_statement"],
        visibility_fn=public_by_default,
        parent_extraction="nesting",
        parent_class_types=frozenset({"class_declaration"}),
        entry_point_patterns=["index.js", "main.js", "app.js", "server.js"],
    ),
}


# ---------------------------------------------------------------------------
# ASTParser
# ---------------------------------------------------------------------------


class ASTParser:
    """Unified AST parser — works for all configured languages via .scm queries."""

    def __init__(self) -> None:
        self._query_cache: dict[str, object] = {}

    def parse_file(self, file_info: FileInfo, source: bytes) -> ParsedFile:
        lang = file_info.language
        config = LANGUAGE_CONFIGS.get(lang)
        language = _get_language(lang)

        if config is None or language is None:
            return ParsedFile(
                file_info=file_info,
                symbols=[],
                imports=[],
                exports=[],
                docstring=None,
                parse_errors=[],
            )

        parser = Parser(language)
        tree = parser.parse(source)
        src = source.decode("utf-8", errors="replace")
        root = tree.root_node

        parse_errors = _collect_error_nodes(root)
        query = self._get_query(lang, language)

        symbols = self._extract_symbols(tree, query, config, file_info, src)
        imports = self._extract_imports(tree, query, config, file_info, src)
        calls = self._extract_calls(tree, query, config, file_info, src, symbols)
        heritage = extract_heritage(tree, query, config, file_info, src, run_query=_run_query)
        exports = self._derive_exports(symbols, config, src)
        docstring = extract_module_docstring(root, src, lang)

        # Compute Aura semantic hash per symbol
        for sym in symbols:
            sym.semantic_hash = sym.compute_semantic_hash()

        return ParsedFile(
            file_info=file_info,
            symbols=symbols,
            imports=imports,
            exports=exports,
            calls=calls,
            heritage=heritage,
            docstring=docstring,
            parse_errors=parse_errors,
        )

    def _get_query(self, lang: str, language: Language) -> object | None:
        if lang in self._query_cache:
            return self._query_cache[lang]

        scm_path = QUERIES_DIR / f"{lang}.scm"
        if not scm_path.exists():
            self._query_cache[lang] = None
            return None

        scm_text = scm_path.read_text(encoding="utf-8")
        try:
            from tree_sitter import Query  # type: ignore[attr-defined]

            compiled = Query(language, scm_text)
            self._query_cache[lang] = compiled
            return compiled
        except Exception as exc:
            log.warning("Failed to compile query", language=lang, error=str(exc))
            self._query_cache[lang] = None
            return None

    def _extract_symbols(
        self,
        tree: object,
        query: object,
        config: LanguageConfig,
        file_info: FileInfo,
        src: str,
    ) -> list[Symbol]:
        if query is None:
            return []

        symbols: list[Symbol] = []
        seen: set[tuple[int, str]] = set()

        for capture_dict in _run_query(query, tree.root_node):  # type: ignore[attr-defined]
            def_nodes = capture_dict.get("symbol.def", [])
            name_nodes = capture_dict.get("symbol.name", [])
            params_nodes = capture_dict.get("symbol.params", [])
            modifier_nodes = capture_dict.get("symbol.modifiers", [])
            receiver_nodes = capture_dict.get("symbol.receiver", [])

            if not def_nodes or not name_nodes:
                continue

            def_node = def_nodes[0]
            name = _node_text(name_nodes[0], src)
            if not name:
                continue

            start_line = def_node.start_point[0] + 1
            dedup_key = (start_line, name)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            node_type = def_node.type
            kind = config.symbol_node_types.get(node_type)
            if kind is None:
                continue

            params_text = _node_text(params_nodes[0], src) if params_nodes else ""

            modifier_texts = [_node_text(m, src) for m in modifier_nodes]
            if def_node.parent and def_node.parent.type == "decorated_definition":
                for sibling in def_node.parent.children:
                    if sibling.type == "decorator":
                        modifier_texts.append(_node_text(sibling, src))
            visibility = config.visibility_fn(name, modifier_texts)

            parent_name = self._find_parent(def_node, config, receiver_nodes, src)

            if parent_name and kind == "function":
                kind = "method"

            signature = build_signature(node_type, name, params_text, def_node, src)
            docstring = extract_symbol_docstring(def_node, src, file_info.language)
            is_async = _is_async_node(def_node, src)

            sym_id = (
                f"{file_info.path}::{parent_name}::{name}"
                if parent_name
                else f"{file_info.path}::{name}"
            )
            qualified = _build_qualified_name(file_info.path, parent_name, name)

            body_text = _node_text(def_node, src)
            symbols.append(
                Symbol(
                    id=sym_id,
                    name=name,
                    qualified_name=qualified,
                    kind=kind,  # type: ignore[arg-type]
                    signature=signature,
                    start_line=start_line,
                    end_line=def_node.end_point[0] + 1,
                    docstring=docstring,
                    decorators=[m for m in modifier_texts if m.startswith("@")],
                    visibility=visibility,  # type: ignore[arg-type]
                    is_async=is_async,
                    language=file_info.language,
                    parent_name=parent_name,
                    body_text=body_text,
                )
            )

        return symbols

    def _find_parent(
        self,
        def_node: Node,
        config: LanguageConfig,
        receiver_nodes: list[Node],
        src: str,
    ) -> str | None:
        if config.parent_extraction in ("nesting", "impl"):
            ancestor = def_node.parent
            while ancestor is not None:
                if ancestor.type in config.parent_class_types:
                    name_node = ancestor.child_by_field_name("name") or (
                        ancestor.child_by_field_name("type")
                    )
                    if name_node:
                        return _node_text(name_node, src)
                ancestor = ancestor.parent
            return None
        return None

    def _extract_imports(
        self,
        tree: object,
        query: object,
        config: LanguageConfig,
        file_info: FileInfo,
        src: str,
    ) -> list[Import]:
        if query is None:
            return []

        imports: list[Import] = []
        seen_raws: set[str] = set()

        for capture_dict in _run_query(query, tree.root_node):  # type: ignore[attr-defined]
            stmt_nodes = capture_dict.get("import.statement", [])
            module_nodes = capture_dict.get("import.module", [])

            if not stmt_nodes or not module_nodes:
                continue

            stmt_node = stmt_nodes[0]
            raw = _node_text(stmt_node, src).strip()
            if raw in seen_raws:
                continue
            seen_raws.add(raw)

            module_text = _node_text(module_nodes[0], src).strip().strip("\"'` ")
            if not module_text:
                continue

            imported_names, bindings = extract_import_bindings(stmt_node, src, file_info.language)
            is_relative = module_text.startswith(".") or module_text.startswith("./")

            imports.append(
                Import(
                    raw_statement=raw,
                    module_path=module_text,
                    imported_names=imported_names,
                    is_relative=is_relative,
                    resolved_file=None,
                    bindings=bindings,
                )
            )

        return imports

    def _extract_calls(
        self,
        tree: object,
        query: object,
        config: LanguageConfig,
        file_info: FileInfo,
        src: str,
        symbols: list[Symbol],
    ) -> list[CallSite]:
        if query is None:
            return []

        spec = _LANG_REGISTRY.get(file_info.language)
        _call_builtins = spec.builtin_calls if spec else frozenset()

        symbol_ranges = sorted(
            [(s.start_line, s.end_line, s.id) for s in symbols],
            key=lambda t: (t[0], -t[1]),
        )

        calls: list[CallSite] = []
        seen: set[tuple[int, str, str | None]] = set()

        for capture_dict in _run_query(query, tree.root_node):  # type: ignore[attr-defined]
            site_nodes = capture_dict.get("call.site", [])
            target_nodes = capture_dict.get("call.target", [])
            arg_nodes = capture_dict.get("call.arguments", [])
            receiver_nodes = capture_dict.get("call.receiver", [])

            if not site_nodes or not target_nodes:
                continue

            site_node = site_nodes[0]
            target_name = _node_text(target_nodes[0], src).strip()
            if not target_name:
                continue

            if target_name in _call_builtins:
                continue

            line = site_node.start_point[0] + 1
            receiver_name = _node_text(receiver_nodes[0], src).strip() if receiver_nodes else None

            dedup_key = (line, target_name, receiver_name)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            arg_count: int | None = None
            if arg_nodes:
                arg_count = _count_arguments(arg_nodes[0])

            caller_id = _find_enclosing_symbol(line, symbol_ranges)

            calls.append(
                CallSite(
                    target_name=target_name,
                    receiver_name=receiver_name,
                    caller_symbol_id=caller_id,
                    line=line,
                    argument_count=arg_count,
                )
            )

        return calls

    def _derive_exports(
        self,
        symbols: list[Symbol],
        config: LanguageConfig,
        src: str,
    ) -> list[str]:
        return [s.name for s in symbols if s.visibility == "public" and s.parent_name is None]


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_DEFAULT_PARSER: ASTParser | None = None


def parse_file(file_info: FileInfo, source: bytes) -> ParsedFile:
    global _DEFAULT_PARSER
    if _DEFAULT_PARSER is None:
        _DEFAULT_PARSER = ASTParser()
    return _DEFAULT_PARSER.parse_file(file_info, source)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_query(query: object, root_node: Node) -> list[dict[str, list[Node]]]:
    results: list[dict[str, list[Node]]] = []
    try:
        from tree_sitter import QueryCursor  # type: ignore[attr-defined]

        cursor = QueryCursor(query)  # type: ignore[call-arg]
        for match in cursor.matches(root_node):
            if hasattr(match, "captures"):
                results.append(match.captures)
            elif isinstance(match, tuple) and len(match) == 2:
                _, caps = match
                results.append(caps)
    except Exception:
        try:
            for item in query.matches(root_node):  # type: ignore[attr-defined]
                if isinstance(item, tuple) and len(item) == 2:
                    _, caps = item
                    results.append(caps)
        except Exception as exc:
            log.warning("query.matches() failed", error=str(exc))
    return results


def _collect_error_nodes(root: Node) -> list[str]:
    errors: list[str] = []

    def _walk(node: Node) -> None:
        if node.type == "ERROR":
            errors.append(f"Parse error at line {node.start_point[0] + 1}")
        for child in node.children:
            _walk(child)

    _walk(root)
    return errors


def _is_async_node(node: Node, src: str) -> bool:
    return node.type == "async_function_definition" or any(c.type == "async" for c in node.children)


def _build_qualified_name(file_path: str, parent_name: str | None, name: str) -> str:
    module = Path(file_path).with_suffix("").as_posix().replace("/", ".")
    if parent_name:
        return f"{module}.{parent_name}.{name}"
    return f"{module}.{name}"


def _count_arguments(arg_node: Node) -> int:
    skip_types = frozenset({"(", ")", ",", "[", "]"})
    return sum(1 for child in arg_node.children if child.type not in skip_types)


def _find_enclosing_symbol(
    line: int,
    symbol_ranges: list[tuple[int, int, str]],
) -> str | None:
    best_id: str | None = None
    best_span = float("inf")

    for start, end, sym_id in symbol_ranges:
        if start > line:
            break
        if start <= line <= end:
            span = end - start
            if span < best_span:
                best_span = span
                best_id = sym_id

    return best_id
