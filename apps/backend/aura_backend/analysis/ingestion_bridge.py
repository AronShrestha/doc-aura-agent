"""Bridge from tree-sitter ingestion to the existing ExtractedArtifact model.

Two outputs:
- ``apply_semantic_hashes`` — annotates existing Python artifacts (produced
  by the legacy ``ast``-based extractor) with a ``semantic_hash`` field
  derived from tree-sitter parse, using (path, name, start_line) match.
- ``extract_js_ts_artifacts`` — produces ``ExtractedArtifact`` objects
  directly for JavaScript/TypeScript files which the legacy extractor
  does not handle.

Callers should invoke both from ``extractors.extract_repo`` so the
existing FastAPI/Pydantic-aware Python extraction stays in place while
gaining: (1) cosmetic-edit-resistant change detection via semantic hash;
(2) multi-language support for JS/TS source files.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

from .ingestion.models import FileInfo, Symbol
from .ingestion.parser import ASTParser
from .types import ExtractedArtifact, ExtractedEdge, RepoSnapshot, SourceFile
from .utils import stable_artifact_id


logger = logging.getLogger(__name__)


# Existing extractors.py canonical_locator convention (Python):
#   module artifact:   "module.path"          (e.g. "aura_backend.routes")
#   function artifact: "module.path.fn"       (e.g. "aura_backend.routes.health")
#   method artifact:   "module.path.Cls.fn"
# Symbol.qualified_name from tree-sitter follows the same format.

_AURA_LANGS = frozenset({"python", "typescript", "javascript"})


def _file_info_for(source: SourceFile) -> FileInfo | None:
    """Map a SourceFile.language string to the ingestion FileInfo language tag.

    The legacy snapshot.py classifies all .ts/.tsx/.jsx as ``"javascript"``.
    Re-classify here so the tree-sitter parser uses the right grammar.
    """
    path = source.path
    if source.language == "python":
        lang = "python"
    elif path.endswith(".ts") or path.endswith(".tsx"):
        lang = "typescript"
    elif path.endswith(".js") or path.endswith(".jsx") or path.endswith(".mjs") or path.endswith(".cjs"):
        lang = "javascript"
    else:
        return None
    return FileInfo(
        path=path,
        abs_path=path,
        language=lang,  # type: ignore[arg-type]
        size_bytes=len(source.text or ""),
        git_hash="",
        last_modified=datetime.now(timezone.utc),
    )


def _parse_files(snapshot: RepoSnapshot) -> dict[str, list[Symbol]]:
    """Run ASTParser over every Python/JS/TS source file.

    Returns ``{path: [symbols]}``. Symbols already have ``semantic_hash``
    populated by ``ASTParser.parse_file``.
    """
    parser = ASTParser()
    out: dict[str, list[Symbol]] = {}
    for source in snapshot.files:
        fi = _file_info_for(source)
        if fi is None:
            continue
        try:
            parsed = parser.parse_file(fi, (source.text or "").encode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "tree-sitter parse failed",
                extra={"path": source.path, "error": str(exc)},
            )
            continue
        out[source.path] = parsed.symbols
    return out


def apply_semantic_hashes(
    artifacts: list[ExtractedArtifact],
    snapshot: RepoSnapshot,
    *,
    parsed: dict[str, list[Symbol]] | None = None,
) -> dict[str, list[Symbol]]:
    """Inject ``semantic_hash`` and ``qualified_name`` into existing artifacts.

    Matches an artifact to a tree-sitter Symbol by ``(source_file,
    source_line_start, name)``. Mutates ``payload`` in place. Returns the
    parsed-symbol map for downstream reuse (avoids re-parsing).
    """
    if parsed is None:
        parsed = _parse_files(snapshot)

    by_path: dict[str, dict[tuple[int, str], Symbol]] = {}
    for path, symbols in parsed.items():
        idx: dict[tuple[int, str], Symbol] = {}
        for sym in symbols:
            idx[(sym.start_line, sym.name)] = sym
            # also index by trailing component of qualified name, w/o line,
            # so the legacy extractor (which sometimes records line=1 for
            # module-level artifacts) can still match
            idx.setdefault((0, sym.name), sym)
        by_path[path] = idx

    matched = 0
    for art in artifacts:
        if not art.source_file or art.source_file not in by_path:
            continue
        line = art.source_line_start or 0
        idx = by_path[art.source_file]
        # Legacy extractor names artifacts as "module.Class.method" (qualified)
        # but stores the bare identifier in payload["simple_name"]. Try both.
        simple = art.payload.get("simple_name") or art.name.rsplit(".", 1)[-1]
        sym = (
            idx.get((line, simple))
            or idx.get((0, simple))
            or idx.get((line, art.name))
            or idx.get((0, art.name))
        )
        if sym is None:
            continue
        art.payload.setdefault("semantic_hash", sym.semantic_hash)
        art.payload.setdefault("qualified_name", sym.qualified_name)
        art.payload.setdefault("kind", sym.kind)
        art.payload.setdefault("language", sym.language)
        art.payload.setdefault("is_async", sym.is_async)
        art.payload.setdefault("decorators", list(sym.decorators))
        art.payload.setdefault("parent_name", sym.parent_name)
        if sym.docstring and "docstring" not in art.payload:
            art.payload["docstring"] = sym.docstring
        if sym.signature and "signature" not in art.payload:
            art.payload["signature"] = sym.signature
        matched += 1

    logger.info(
        "tree-sitter hashes applied",
        extra={"event": "ts_hashes_applied", "matched": matched, "total": len(artifacts)},
    )
    return parsed


def extract_js_ts_artifacts(
    snapshot: RepoSnapshot,
    *,
    parsed: dict[str, list[Symbol]] | None = None,
) -> tuple[list[ExtractedArtifact], list[ExtractedEdge]]:
    """Produce artifacts and edges for JavaScript/TypeScript source files.

    The legacy ``extractors._extract_python`` does not run on JS/TS, so
    those files would otherwise produce zero artifacts. This function
    fills the gap with one artifact per top-level symbol plus heritage
    edges. Imports are not converted to edges here — call
    ``extract_repo``'s import resolver still owns that.
    """
    if parsed is None:
        parsed = _parse_files(snapshot)

    artifacts: list[ExtractedArtifact] = []
    edges: list[ExtractedEdge] = []

    for source in snapshot.files:
        path = source.path
        if path not in parsed:
            continue
        if not (path.endswith(".ts") or path.endswith(".tsx")
                or path.endswith(".js") or path.endswith(".jsx")
                or path.endswith(".mjs") or path.endswith(".cjs")):
            continue

        symbols = parsed[path]
        # module artifact for the file
        module_name = _module_name_for_js_ts(path)
        module_aid = stable_artifact_id(snapshot.repo_id, "module", module_name)
        artifacts.append(
            ExtractedArtifact(
                artifact_id=module_aid,
                category="module",
                name=module_name,
                canonical_locator=module_name,
                source_file=path,
                source_line_start=1,
                source_line_end=max(1, source.loc),
                payload={
                    "language": symbols[0].language if symbols else "javascript",
                    "loc": source.loc,
                    "source_hash": source.source_hash,
                    "imports": source.imports,
                    "exports": [s.name for s in symbols if s.parent_name is None],
                    "parse_errors": source.parse_errors,
                },
            )
        )

        for sym in symbols:
            category = _symbol_kind_to_category(sym.kind)
            qualified = sym.qualified_name
            aid = stable_artifact_id(snapshot.repo_id, category, qualified)
            artifacts.append(
                ExtractedArtifact(
                    artifact_id=aid,
                    category=category,
                    name=sym.name,
                    canonical_locator=qualified,
                    source_file=path,
                    source_line_start=sym.start_line,
                    source_line_end=sym.end_line,
                    payload={
                        "language": sym.language,
                        "kind": sym.kind,
                        "qualified_name": qualified,
                        "parent_name": sym.parent_name,
                        "signature": sym.signature,
                        "docstring": sym.docstring,
                        "decorators": list(sym.decorators),
                        "is_async": sym.is_async,
                        "visibility": sym.visibility,
                        "semantic_hash": sym.semantic_hash,
                    },
                )
            )
            # belongs-to edge from module → symbol
            edges.append(ExtractedEdge(module_aid, aid, "uses_model" if category in ("class", "data_model") else "calls"))

    return artifacts, edges


def parse_all(snapshot: RepoSnapshot) -> dict[str, list[Symbol]]:
    """Public helper so callers can run a single parse pass and reuse it."""
    return _parse_files(snapshot)


def _module_name_for_js_ts(path: str) -> str:
    no_ext = path
    for ext in (".tsx", ".ts", ".jsx", ".js", ".mjs", ".cjs"):
        if no_ext.endswith(ext):
            no_ext = no_ext[: -len(ext)]
            break
    return no_ext.replace("/", ".")


_KIND_TO_CATEGORY: dict[str, str] = {
    "function": "function",
    "method": "function",
    "class": "data_model",  # closest existing category — refined later
    "interface": "data_model",
    "enum": "data_model",
    "type_alias": "data_model",
    "constant": "config",
    "variable": "config",
    "module": "module",
    "struct": "data_model",
    "trait": "data_model",
    "impl": "function",
    "decorator": "function",
}


def _symbol_kind_to_category(kind: str) -> str:
    return _KIND_TO_CATEGORY.get(kind, "function")
