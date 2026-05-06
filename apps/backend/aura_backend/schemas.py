from pydantic import BaseModel, Field
from typing import Literal


class AnalyzeRepoRequest(BaseModel):
    installation_id: str | None = None
    github_repo_id: str
    branch: str | None = None
    commit_sha: str | None = None


class AnalyzeRepoResponse(BaseModel):
    run_id: int
    repo_id: int
    status: Literal["queued"]


class RunResponse(BaseModel):
    run_id: int
    repo_id: int
    status: str
    stage: str
    progress: int
    error: str | None = None
    quality_report: dict | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = 20


class Provenance(BaseModel):
    source_file: str
    source_line_start: int | None = None
    source_line_end: int | None = None
    confidence: float = 1.0


class DocSectionResponse(BaseModel):
    section_id: str
    title: str
    diataxis_type: str
    content_md: str
    provenance: list[Provenance]


class ArtifactResponse(BaseModel):
    artifact_id: str
    category: str
    name: str
    source_file: str | None = None
    source_line_start: int | None = None
    source_line_end: int | None = None
    payload: dict


class GeneratedDocResponse(BaseModel):
    artifact_id: str
    category: str
    title: str
    slug_path: str
    content_hash: str
    source_files: list[str]
    source_lines: dict
    content_md: str
