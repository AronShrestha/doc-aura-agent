from __future__ import annotations

from pathlib import Path
from typing import Any

from ..types import ExtractedArtifact, ExtractedEdge, RepoSnapshot, SourceFile


MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def compact_repo_context(
    snapshot: RepoSnapshot,
    artifacts: list[ExtractedArtifact],
    edges: list[ExtractedEdge],
    summary: dict[str, Any],
    max_artifacts: int = 120,
) -> dict[str, Any]:
    return {
        "repo_id": snapshot.repo_id,
        "repo_sha": snapshot.repo_sha,
        "frameworks": snapshot.frameworks,
        "summary": summary,
        "files": [
            {
                "path": f.path,
                "language": f.language,
                "loc": f.loc,
                "source_hash": f.source_hash,
                "top_level_symbols": f.top_level_symbols[:30],
                "imports": f.imports[:30],
                "parse_errors": f.parse_errors,
                "source_excerpt": _source_excerpt(f),
            }
            for f in snapshot.files[:200]
        ],
        "artifacts": [artifact_context(a) for a in sorted(artifacts, key=lambda a: (a.category, a.name))[:max_artifacts]],
        "edges": [
            {"source": e.src_artifact_id, "target": e.dst_artifact_id, "kind": e.kind}
            for e in edges[:500]
        ],
    }


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
