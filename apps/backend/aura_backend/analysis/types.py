from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SourceFile:
    path: str
    language: str
    loc: int
    source_hash: str
    text: str
    top_level_symbols: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RepoSnapshot:
    root: Path
    repo_id: int
    repo_sha: str
    files: list[SourceFile]
    frameworks: list[str]

    @property
    def total_loc(self) -> int:
        return sum(f.loc for f in self.files)


@dataclass(slots=True)
class ExtractedArtifact:
    artifact_id: str
    category: str
    name: str
    canonical_locator: str
    source_file: str | None
    source_line_start: int | None
    source_line_end: int | None
    payload: dict[str, Any]


@dataclass(slots=True)
class ExtractedEdge:
    src_artifact_id: str
    dst_artifact_id: str
    kind: str


@dataclass(slots=True)
class GeneratedDocDraft:
    artifact_id: str
    category: str
    title: str
    slug_path: str
    content_md: str
    content_hash: str
    source_files: list[str]
    source_lines: dict[str, list[int | None]]


@dataclass(slots=True)
class AnalysisResult:
    snapshot: RepoSnapshot
    artifacts: list[ExtractedArtifact]
    edges: list[ExtractedEdge]
    docs: list[GeneratedDocDraft]
    manifest: dict[str, Any]
    quality_report: dict[str, Any]
