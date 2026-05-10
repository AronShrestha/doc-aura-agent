from __future__ import annotations
from datetime import datetime
from sqlalchemy import Boolean, String, Integer, DateTime, ForeignKey, LargeBinary, Text, JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    github_user_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GithubOAuthToken(Base):
    __tablename__ = "github_oauth_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    access_token: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GithubInstallation(Base):
    __tablename__ = "github_installations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    installation_id: Mapped[str] = mapped_column(String(64), index=True)
    account_login: Mapped[str] = mapped_column(String(255))
    account_type: Mapped[str] = mapped_column(String(64), default="User")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Repo(Base):
    __tablename__ = "repos"
    __table_args__ = (UniqueConstraint("user_id", "github_repo_id", name="uq_repo_user_github"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    github_repo_id: Mapped[str] = mapped_column(String(64), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    default_branch: Mapped[str] = mapped_column(String(128), default="main")
    installation_id: Mapped[str] = mapped_column(String(64), index=True)
    owner: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    branch: Mapped[str] = mapped_column(String(128), default="main")
    commit_sha: Mapped[str] = mapped_column(String(128), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    activity: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_pr_run: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    artifact_id: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ArtifactEdge(Base):
    __tablename__ = "artifact_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    src_artifact_id: Mapped[str] = mapped_column(String(128), index=True)
    dst_artifact_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(64))


class DocSection(Base):
    __tablename__ = "doc_sections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    section_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(255))
    diataxis_type: Mapped[str] = mapped_column(String(64))
    content_md: Mapped[str] = mapped_column(Text)
    provenance: Mapped[list] = mapped_column(JSON)


class GeneratedDoc(Base):
    __tablename__ = "generated_docs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    artifact_id: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    slug_path: Mapped[str] = mapped_column(String(500), index=True)
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    generated_sha: Mapped[str] = mapped_column(String(128), default="")
    last_verified_sha: Mapped[str] = mapped_column(String(128), default="")
    source_files: Mapped[list] = mapped_column(JSON)
    source_lines: Mapped[dict] = mapped_column(JSON)
    content_md: Mapped[str] = mapped_column(Text)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocMapping(Base):
    __tablename__ = "doc_mappings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    artifact_id: Mapped[str] = mapped_column(String(128), index=True)
    doc_path: Mapped[str] = mapped_column(String(500), index=True)
    content_hash: Mapped[str] = mapped_column(String(128), index=True)


class PullRequest(Base):
    __tablename__ = "pull_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), index=True)
    github_pr_id: Mapped[str] = mapped_column(String(64), index=True)
    number: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    state: Mapped[str] = mapped_column(String(64), default="open")
    base_ref: Mapped[str] = mapped_column(String(255), default="")
    base_sha: Mapped[str] = mapped_column(String(128), default="")
    head_ref: Mapped[str] = mapped_column(String(255), default="")
    head_sha: Mapped[str] = mapped_column(String(128), default="")
    html_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    merged: Mapped[bool] = mapped_column(Boolean, default=False)
    comment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PrAnalysisRun(Base):
    __tablename__ = "pr_analysis_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    base_run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id"), nullable=True)
    head_run_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_runs.id"), nullable=True)
    impact_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    review_comment_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    shadow_pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    shadow_pr_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shadow_pr_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    shadow_pr_file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    code_patches: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mismatch_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dashboard_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DriftReport(Base):
    __tablename__ = "drift_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    report: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocDiff(Base):
    __tablename__ = "doc_diffs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pr_analysis_run_id: Mapped[int] = mapped_column(ForeignKey("pr_analysis_runs.id"), index=True)
    artifact_id: Mapped[str] = mapped_column(String(128), index=True)
    doc_path: Mapped[str] = mapped_column(String(500))
    change_type: Mapped[str] = mapped_column(String(64))
    impact_tier: Mapped[str] = mapped_column(String(16), default="Medium", index=True)
    affected_symbol_ids: Mapped[list] = mapped_column(JSON, default=list)
    unified_diff: Mapped[str] = mapped_column(Text)
    side_by_side: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
