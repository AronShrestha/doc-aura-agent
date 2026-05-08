"""Shared data models for the ingestion pipeline.

Plain dataclasses (not Pydantic) for speed. Lifted + trimmed from
repowise (AGPL-3.0). Aura adds a ``semantic_hash`` field to ``Symbol``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, get_args

from .languages.registry import REGISTRY as _REGISTRY


# ---------------------------------------------------------------------------
# Language tags (Aura MVP: Python + JS + TS only, plus passthrough/unknown)
# ---------------------------------------------------------------------------

LanguageTag = Literal[
    "python",
    "typescript",
    "javascript",
    "yaml",
    "json",
    "toml",
    "markdown",
    "unknown",
]

_LANGUAGE_TAG_VALUES: frozenset[str] = frozenset(get_args(LanguageTag))

EXTENSION_TO_LANGUAGE: dict[str, LanguageTag] = {
    ext: tag  # type: ignore[misc]
    for ext, tag in _REGISTRY.all_extensions().items()
    if tag in _LANGUAGE_TAG_VALUES
}

SPECIAL_FILENAMES: dict[str, LanguageTag] = {
    fn: tag  # type: ignore[misc]
    for fn, tag in _REGISTRY.all_special_filenames().items()
    if tag in _LANGUAGE_TAG_VALUES
}


# ---------------------------------------------------------------------------
# Symbol kinds
# ---------------------------------------------------------------------------

SymbolKind = Literal[
    "function",
    "class",
    "method",
    "interface",
    "enum",
    "constant",
    "type_alias",
    "decorator",
    "trait",
    "impl",
    "struct",
    "module",
    "macro",
    "variable",
]


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------


@dataclass
class FileInfo:
    """Metadata about a single source file discovered during traversal."""

    path: str  # POSIX path relative to repo root
    abs_path: str  # absolute filesystem path
    language: LanguageTag
    size_bytes: int
    git_hash: str = ""
    last_modified: datetime | None = None
    is_test: bool = False
    is_config: bool = False
    is_api_contract: bool = False
    is_entry_point: bool = False


@dataclass
class PackageInfo:
    name: str
    path: str
    language: LanguageTag
    entry_points: list[str]
    manifest_file: str


@dataclass
class RepoStructure:
    is_monorepo: bool
    packages: list[PackageInfo]
    root_language_distribution: dict[str, float]
    total_files: int
    total_loc: int
    entry_points: list[str]


@dataclass
class Symbol:
    """A code symbol (function, class, method, …) extracted from a file."""

    id: str  # "<rel_path>::<name>" or "<rel_path>::<class>::<method>"
    name: str
    qualified_name: str
    kind: SymbolKind
    signature: str
    start_line: int
    end_line: int
    docstring: str | None
    decorators: list[str] = field(default_factory=list)
    visibility: Literal["public", "private", "protected", "internal"] = "public"
    is_async: bool = False
    complexity_estimate: int = 1
    language: str = ""
    parent_name: str | None = None
    body_text: str = ""  # raw def_node.text — used for semantic hash
    semantic_hash: str = ""  # Aura: stable hash gating cosmetic changes

    def compute_semantic_hash(self) -> str:
        """Stable hash over signature + decorators + normalized body text.

        Body text has comments + docstring + whitespace stripped, so:
        - Renamed *locals* still affect the hash (we WANT that — variable
          renames may signal behavior change in dynamic languages).
        - Added/removed comments do NOT change the hash.
        - Reformatting (whitespace, line breaks) does NOT change the hash.
        - Adding a return value, calling a different function, changing
          a literal → DOES change the hash.
        """
        sig_norm = _normalize_signature(self.signature)
        body_norm = _normalize_body(self.body_text, self.language)
        parts = "|".join(
            [
                self.name,
                self.kind,
                self.parent_name or "",
                sig_norm,
                ",".join(sorted(self.decorators)),
                "async" if self.is_async else "sync",
                body_norm,
            ]
        )
        return hashlib.sha256(parts.encode("utf-8")).hexdigest()


_WS_RE = re.compile(r"\s+")
_PUNCT_WS_RE = re.compile(r"\s*([(),:\[\]{}=])\s*")
_PY_DOCSTRING_RE = re.compile(
    r'(?P<q>"""|\'\'\'|"|\')\s*[\s\S]*?(?P=q)',
)
_PY_TRIPLE_DOC_RE = re.compile(r'(?P<q>"""|\'\'\')[\s\S]*?(?P=q)')


def _normalize_body(body: str, language: str) -> str:
    """Strip comments + docstrings + whitespace from a definition's source.

    Conservative — keeps identifiers, literals, operators. Two definitions
    with identical AST shape and identical literals produce identical
    normalized strings. Reformatting + comment edits collapse to the same
    output.
    """
    if not body:
        return ""
    text = body
    if language == "python":
        # Strip triple-quoted docstrings (greedy match limited to one)
        text = _PY_TRIPLE_DOC_RE.sub("", text, count=2)
        # Strip line comments
        text = re.sub(r"#[^\n]*", "", text)
    elif language in ("typescript", "javascript"):
        # Block comments first (greedy across lines), then line comments
        text = re.sub(r"/\*[\s\S]*?\*/", "", text)
        text = re.sub(r"//[^\n]*", "", text)
    # Collapse whitespace + drop whitespace adjacent to punctuation
    text = _WS_RE.sub(" ", text).strip()
    text = _PUNCT_WS_RE.sub(r"\1", text)
    return text


def _normalize_signature(sig: str) -> str:
    """Strip comments, collapse whitespace, drop whitespace adjacent to punctuation.

    Goal: two signatures that differ only in formatting produce the same
    normalized string, so ``Symbol.compute_semantic_hash`` is invariant
    under cosmetic edits.
    """
    if not sig:
        return ""
    no_hash = re.sub(r"#.*", "", sig)
    no_block = re.sub(r"/\*.*?\*/", "", no_hash, flags=re.DOTALL)
    no_line = re.sub(r"//.*", "", no_block)
    collapsed = _WS_RE.sub(" ", no_line).strip()
    return _PUNCT_WS_RE.sub(r"\1", collapsed)


@dataclass
class NamedBinding:
    local_name: str
    exported_name: str | None = None
    source_file: str | None = None
    is_module_alias: bool = False
    is_global: bool = False
    is_static_import: bool = False


@dataclass
class Import:
    raw_statement: str
    module_path: str
    imported_names: list[str]
    is_relative: bool
    resolved_file: str | None = None
    bindings: list[NamedBinding] = field(default_factory=list)


@dataclass
class CallSite:
    target_name: str
    receiver_name: str | None
    caller_symbol_id: str | None
    line: int
    argument_count: int | None = None


HeritageKind = Literal["extends", "implements", "trait_impl", "mixin"]


@dataclass
class HeritageRelation:
    child_name: str
    parent_name: str
    kind: HeritageKind
    line: int


EdgeType = Literal[
    "imports",
    "defines",
    "calls",
    "has_method",
    "has_property",
    "extends",
    "implements",
    "method_overrides",
    "method_implements",
    "co_changes",
    "framework",
    "dynamic",
]


@dataclass
class ParsedFile:
    file_info: FileInfo
    symbols: list[Symbol]
    imports: list[Import]
    exports: list[str]
    calls: list[CallSite] = field(default_factory=list)
    heritage: list[HeritageRelation] = field(default_factory=list)
    docstring: str | None = None
    parse_errors: list[str] = field(default_factory=list)
    content_hash: str = ""


def compute_content_hash(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()
