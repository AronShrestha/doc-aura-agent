"""Language specification dataclass — pure data, no behaviour.

``LanguageSpec`` captures everything Aura needs to know about a
language's *identity*: file extensions, classification flags, ecosystem
metadata, builtin symbols, and display properties.

Lifted from repowise (AGPL-3.0). See
``/tmp/repowise/packages/core/src/repowise/core/ingestion/languages/spec.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LanguageSpec:
    """Complete identity specification for a single language."""

    # -- Identity --------------------------------------------------------
    tag: str  # matches LanguageTag literal
    display_name: str  # "Python", "TypeScript"

    # -- File matching ---------------------------------------------------
    extensions: frozenset[str] = field(default_factory=frozenset)
    special_filenames: frozenset[str] = field(default_factory=frozenset)

    # -- Classification --------------------------------------------------
    is_code: bool = True
    is_infra: bool = False
    is_passthrough: bool = False
    is_api_contract: bool = False

    # -- Tree-sitter -----------------------------------------------------
    # Grammars come from tree-sitter-language-pack, looked up by tag
    # via get_language()/get_parser(). grammar_package/loader fields
    # retained for compatibility with the ASTParser; we ignore them.
    grammar_package: str | None = None
    grammar_loader: str = "language"
    scm_file: str | None = None
    shares_grammar_with: str | None = None

    # -- Heritage --------------------------------------------------------
    heritage_node_types: frozenset[str] = field(default_factory=frozenset)

    # -- Ecosystem -------------------------------------------------------
    entry_point_patterns: tuple[str, ...] = ()
    manifest_files: tuple[str, ...] = ()
    lock_files: tuple[str, ...] = ()
    generated_suffixes: tuple[str, ...] = ()
    shebang_tokens: tuple[str, ...] = ()
    blocked_dirs: tuple[str, ...] = ()
    blocked_extensions: tuple[str, ...] = ()

    # -- Builtins --------------------------------------------------------
    builtin_calls: frozenset[str] = field(default_factory=frozenset)
    builtin_parents: frozenset[str] = field(default_factory=frozenset)

    # -- Display ---------------------------------------------------------
    color_hex: str = "#8b5cf6"
