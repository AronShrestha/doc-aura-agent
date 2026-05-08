from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dataclasses import asdict, is_dataclass

from ..types import ExtractedArtifact, ExtractedEdge, RepoSnapshot, SourceFile


MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Conservative payload-size budget so we stay well under the chat-model
# context window (Qwen2.5-Coder-32B = 32 k tokens). We aim for ~60 k chars
# of JSON ≈ 15 k tokens, leaving room for system prompt + completion.
_DEFAULT_BUDGET_CHARS = int(os.getenv("AURA_CONTEXT_BUDGET_CHARS", "60000"))


def compact_repo_context(
    snapshot: RepoSnapshot,
    artifacts: list[ExtractedArtifact],
    edges: list[ExtractedEdge],
    summary: dict[str, Any],
    max_artifacts: int = 120,
    budget_chars: int = _DEFAULT_BUDGET_CHARS,
) -> dict[str, Any]:
    """Build the LLM prompt payload while respecting a char budget.

    Strategy: pack high-signal items first (summary, frameworks, artifacts
    by importance, edges, files w/ source excerpts) and stop once the
    serialized JSON would exceed ``budget_chars``. Source excerpts are
    the heaviest section so they get trimmed last.
    """
    base: dict[str, Any] = {
        "repo_id": snapshot.repo_id,
        "repo_sha": snapshot.repo_sha,
        "frameworks": snapshot.frameworks,
        "summary": summary,
        "artifacts": [],
        "edges": [],
        "files": [],
    }

    # Artifacts first — most signal-dense; truncate to max_artifacts.
    sorted_arts = sorted(artifacts, key=lambda a: (a.category, a.name))[:max_artifacts]
    for a in sorted_arts:
        base["artifacts"].append(artifact_context(a))
        if len(json.dumps(base)) > budget_chars * 0.5:
            break

    # Edges — capped at 500 or until budget gets tight.
    for e in edges[:500]:
        base["edges"].append({"source": e.src_artifact_id, "target": e.dst_artifact_id, "kind": e.kind})
        if len(json.dumps(base)) > budget_chars * 0.6:
            break

    # Files — top-level symbols always; source excerpts only while budget left.
    files_meta = []
    for f in snapshot.files[:200]:
        files_meta.append({
            "path": f.path,
            "language": f.language,
            "loc": f.loc,
            "source_hash": f.source_hash,
            "top_level_symbols": f.top_level_symbols[:30],
            "imports": f.imports[:30],
            "parse_errors": f.parse_errors,
            "source_excerpt": "",
        })
    base["files"] = files_meta

    if len(json.dumps(base)) >= budget_chars:
        # Trim files until we fit
        while base["files"] and len(json.dumps(base)) > budget_chars:
            base["files"].pop()
        return base

    # Add source excerpts from the front of the file list, shrinking as
    # we approach the budget.
    remaining = budget_chars - len(json.dumps(base))
    for fmeta, f in zip(base["files"], snapshot.files[: len(base["files"])]):
        if remaining <= 0:
            break
        excerpt = _source_excerpt(f, max_chars=min(1800, max(200, remaining // 4)))
        fmeta["source_excerpt"] = excerpt
        remaining -= len(excerpt)

    # Final safety check
    while len(json.dumps(base)) > budget_chars and base["files"]:
        last = base["files"][-1]
        if last.get("source_excerpt"):
            last["source_excerpt"] = ""
            continue
        base["files"].pop()

    return base


def artifact_context(artifact: ExtractedArtifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "category": artifact.category,
        "name": artifact.name,
        "canonical_locator": artifact.canonical_locator,
        "source_file": artifact.source_file,
        "source_line_start": artifact.source_line_start,
        "source_line_end": artifact.source_line_end,
        "payload": artifact.payload,
    }


def discover_media_files(snapshot: RepoSnapshot, limit: int = 20) -> list[Path]:
    media: list[Path] = []
    for path in sorted(snapshot.root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in MEDIA_SUFFIXES:
            continue
        if any(part in {"node_modules", ".git", ".venv", "__pycache__"} for part in path.parts):
            continue
        if path.stat().st_size > 3_000_000:
            continue
        media.append(path)
        if len(media) >= limit:
            break
    return media


def _source_excerpt(source: SourceFile, max_chars: int = 1800) -> str:
    if source.language not in {"python", "markdown", "json", "toml", "yaml", "javascript", "env", "dockerfile"}:
        return ""
    return source.text[:max_chars]


def project_summary_context(
    snapshot: RepoSnapshot,
    aggs,
    spec,
    *,
    human_docs: list[ExtractedArtifact] | None = None,
    budget_chars: int = _DEFAULT_BUDGET_CHARS,
    entity_focus: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pack only the aggregation slices a doc-type spec requires.

    ``aggs`` is a ``ProjectAggregations`` and ``spec`` a ``DocTypeSpec``.
    Result is a JSON-serializable dict capped to ``budget_chars``.

    When ``entity_focus`` is set, aggregation rows are filtered down to the
    targeted entity so per-entity writers see narrow, dense context.
    """
    payload: dict[str, Any] = {
        "repo_sha": snapshot.repo_sha,
        "frameworks": list(snapshot.frameworks),
        "doc_type": spec.id,
        "title": spec.title,
        "diataxis": spec.diataxis,
        "task_brief": spec.task_brief,
        "body_outline": list(spec.body_outline),
        "target_path": spec.output_path_template,
        "aggregations": {},
        "human_docs": [],
        "entity_focus": entity_focus or {},
    }
    for name in spec.required_aggregations:
        value = getattr(aggs, name, None)
        if value is None:
            continue
        serialized = _agg_to_serializable(value)
        if entity_focus:
            serialized = _narrow_for_entity(name, serialized, entity_focus)
        payload["aggregations"][name] = serialized

    if human_docs:
        for doc in human_docs[:6]:
            payload["human_docs"].append(
                {
                    "path": doc.source_file,
                    "headings": (doc.payload or {}).get("headings", [])[:30],
                    "line_range": [doc.source_line_start, doc.source_line_end],
                }
            )

    # Budget enforcement: progressively trim aggregation entries by row count
    # rather than truncating mid-structure.
    while len(json.dumps(payload, default=str)) > budget_chars and payload["aggregations"]:
        largest = max(
            payload["aggregations"].items(),
            key=lambda kv: len(json.dumps(kv[1], default=str)),
        )
        key, value = largest
        if isinstance(value, list) and len(value) > 4:
            payload["aggregations"][key] = value[: max(1, len(value) // 2)]
        elif isinstance(value, dict):
            for sub_key, sub_val in list(value.items()):
                if isinstance(sub_val, list) and len(sub_val) > 4:
                    payload["aggregations"][key][sub_key] = sub_val[: max(1, len(sub_val) // 2)]
                    break
            else:
                payload["aggregations"].pop(key)
        else:
            payload["aggregations"].pop(key)
    return payload


def _narrow_for_entity(
    agg_name: str,
    value: Any,
    entity_focus: dict[str, Any],
) -> Any:
    """Trim an aggregation slice down to rows matching the entity_focus.

    Per-entity writers only care about ONE row plus very small cross-refs
    (e.g. an endpoint detail wants its own row plus the response model).
    Falling back to the full slice keeps unrelated docs unaffected.
    """
    kind = entity_focus.get("kind")
    key = entity_focus.get("key")
    name = entity_focus.get("name")

    if kind == "data_model" and agg_name == "data_model_graph" and isinstance(value, dict):
        models = value.get("models") or []
        match = [m for m in models if m.get("artifact_id") == key or m.get("name") == name]
        refs = value.get("references") or []
        related_names = set()
        for r in refs:
            if r.get("source") == name or r.get("target") == name:
                related_names.add(r.get("source"))
                related_names.add(r.get("target"))
        related = [m for m in models if m.get("name") in related_names and m.get("name") != name]
        return {
            "models": match + related[:5],
            "references": [r for r in refs if r.get("source") == name or r.get("target") == name],
        }

    if kind == "env_var" and agg_name == "env_var_inventory" and isinstance(value, list):
        return [v for v in value if v.get("var") == key]

    if kind == "endpoint" and agg_name == "endpoint_catalog" and isinstance(value, list):
        method = entity_focus.get("method")
        path = entity_focus.get("path")
        out = []
        for group in value:
            kept = [
                e for e in (group.get("endpoints") or [])
                if e.get("method") == method and e.get("path") == path
            ]
            if kept:
                out.append({"prefix": group.get("prefix"), "endpoints": kept})
        return out
    if kind == "endpoint" and agg_name == "data_model_graph" and isinstance(value, dict):
        # Keep all models — endpoint detail may reference its response model.
        return value

    if kind == "config_file" and agg_name == "config_inventory" and isinstance(value, list):
        return [c for c in value if c.get("path") == key]
    if kind == "config_file" and agg_name == "env_var_inventory" and isinstance(value, list):
        return [v for v in value if key in (v.get("defining_config_files") or [])]

    if kind == "module" and agg_name == "module_responsibility_map" and isinstance(value, list):
        return [m for m in value if m.get("package_path") == key]
    if kind == "module" and agg_name == "endpoint_catalog" and isinstance(value, list):
        # Keep only endpoint groups whose handlers live in this module.
        out = []
        prefix = str(key) + "."
        for group in value:
            kept = [
                e for e in (group.get("endpoints") or [])
                if (e.get("handler_qn") or "").startswith(prefix)
            ]
            if kept:
                out.append({"prefix": group.get("prefix"), "endpoints": kept})
        return out
    if kind == "module" and agg_name == "workflow_traces" and isinstance(value, list):
        return [w for w in value if any(str(key) in step for step in (w.get("path") or []))]

    return value


def _agg_to_serializable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, list):
        return [_agg_to_serializable(item) for item in value]
    if isinstance(value, dict):
        return {k: _agg_to_serializable(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_agg_to_serializable(item) for item in value]
    return value
