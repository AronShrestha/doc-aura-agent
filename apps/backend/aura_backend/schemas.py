from pydantic import BaseModel, EmailStr, Field
from typing import Literal


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    display_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserPublic(BaseModel):
    id: int
    email: EmailStr
    display_name: str | None = None
    phone: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserPublic


class MeResponse(BaseModel):
    id: int
    email: EmailStr
    display_name: str | None = None
    phone: str | None = None
    github_linked: bool
    github_login: str | None = None


class RepoSummary(BaseModel):
    repo_id: int
    github_repo_id: str
    full_name: str
    default_branch: str
    latest_run: dict | None = None


class MyReposResponse(BaseModel):
    repos: list[RepoSummary]


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
    repo_full_name: str | None = None
    status: str
    stage: str
    progress: int
    error: str | None = None
    quality_report: dict | None = None
    activity: list[dict] | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = 20


class DocChatHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class DocChatRequest(BaseModel):
    message: str = Field(min_length=1)
    active_doc_id: str | None = None
    history: list[DocChatHistoryItem] = Field(default_factory=list)


class DocChatLink(BaseModel):
    doc_id: str
    title: str
    anchor: str | None = None
    section_title: str | None = None


class DocChatResponse(BaseModel):
    answer: str
    links: list[DocChatLink] = Field(default_factory=list)


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
