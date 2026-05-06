from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, UTC
from typing import Any

from .clients import TextModelClient
from .context import artifact_context
from .models import PlannedDoc, VisualContext
from .parsing import markdown_from_text
from ..types import ExtractedArtifact, GeneratedDocDraft, RepoSnapshot
from ..utils import sha256_text


logger = logging.getLogger(__name__)


async def run_artifact_writer_agent(
    llm: TextModelClient,
    snapshot: RepoSnapshot,
    planned_doc: PlannedDoc,
    source_artifacts: list[ExtractedArtifact],
    repo_analysis: dict[str, Any],
    visual_context: list[VisualContext],
    generated_at: str,
) -> GeneratedDocDraft:
    logger.info("artifact writer started", extra={"repo_id": snapshot.repo_id, "agent": "artifact_writer"})
    messages = [
        {
            "role": "system",
            "content": (
                "You are Aura's Artifact Writer Agent. Write precise Markdown reference documentation. "
                "Use only supplied static facts and visual context. Do not invent behavior. "
                "Return Markdown only, no YAML front matter. Include Source Provenance."
            ),
        },
        {"role": "user", "content": _writer_context(snapshot, planned_doc, source_artifacts, repo_analysis, visual_context)},
    ]
    raw = await llm.complete(messages, temperature=0.15)
    draft = _draft_from_markdown(snapshot, planned_doc, source_artifacts, markdown_from_text(raw), generated_at)
    logger.info("artifact writer succeeded", extra={"repo_id": snapshot.repo_id, "agent": "artifact_writer"})
    return draft


async def run_system_writer_agent(
    llm: TextModelClient,
    snapshot: RepoSnapshot,
    planned_doc: PlannedDoc,
    source_artifacts: list[ExtractedArtifact],
    repo_analysis: dict[str, Any],
    visual_context: list[VisualContext],
    generated_at: str,
) -> GeneratedDocDraft:
    logger.info("system writer started", extra={"repo_id": snapshot.repo_id, "agent": "system_writer"})
    messages = [
        {
            "role": "system",
            "content": (
                "You are Aura's System Writer Agent. Write useful living documentation selected by the planner. "
                "Use Diataxis type requested in the plan. Use only supplied static facts and VLM descriptions; "
                "images are context, not code truth. Return Markdown only, no YAML front matter. Include Source Provenance."
            ),
        },
        {"role": "user", "content": _writer_context(snapshot, planned_doc, source_artifacts, repo_analysis, visual_context)},
    ]
    raw = await llm.complete(messages, temperature=0.2)
    draft = _draft_from_markdown(snapshot, planned_doc, source_artifacts, markdown_from_text(raw), generated_at)
    logger.info("system writer succeeded", extra={"repo_id": snapshot.repo_id, "agent": "system_writer"})
    return draft


def make_index_doc(snapshot: RepoSnapshot, docs: list[GeneratedDocDraft], generated_at: str) -> GeneratedDocDraft:
    content = "# Aura Documentation Index\n\n"
    for doc in sorted(docs, key=lambda d: (d.category, d.title)):
        content += f"- [{doc.title}]({doc.slug_path.removeprefix('.aura/docs/')})\n"
    full = _front_matter("index", "index", "Documentation Index", [], {}, generated_at, snapshot.repo_sha, content) + "\n" + content
    return GeneratedDocDraft(
        artifact_id="index",
        category="index",
        title="Documentation Index",
        slug_path=".aura/docs/index.md",
        content_md=full,
        content_hash=sha256_text(full),
        source_files=[],
        source_lines={},
    )


def _writer_context(
    snapshot: RepoSnapshot,
    planned_doc: PlannedDoc,
    source_artifacts: list[ExtractedArtifact],
    repo_analysis: dict[str, Any],
    visual_context: list[VisualContext],
) -> str:
    return json.dumps(
        {
            "repo_sha": snapshot.repo_sha,
            "frameworks": snapshot.frameworks,
            "planned_doc": asdict(planned_doc),
            "source_artifacts": [artifact_context(a) for a in source_artifacts],
            "repo_analysis": repo_analysis,
            "visual_context": [asdict(v) for v in visual_context if planned_doc.uses_vlm_context],
            "requirements": {
                "front_matter": "Do not write front matter; Aura adds it.",
                "provenance": "Include Source Provenance with source files and lines when available.",
                "diataxis_type": planned_doc.diataxis_type,
            },
        },
        sort_keys=True,
    )


def _draft_from_markdown(
    snapshot: RepoSnapshot,
    planned_doc: PlannedDoc,
    source_artifacts: list[ExtractedArtifact],
    body: str,
    generated_at: str,
) -> GeneratedDocDraft:
    if not body.strip():
        raise RuntimeError(f"empty_agent_doc:{planned_doc.doc_id}")
    source_files = sorted({a.source_file for a in source_artifacts if a.source_file})
    source_lines = {
        a.source_file: [a.source_line_start, a.source_line_end]
        for a in source_artifacts
        if a.source_file
    }
    front = _front_matter(
        planned_doc.doc_id,
        planned_doc.category,
        planned_doc.title,
        source_files,
        source_lines,
        generated_at,
        snapshot.repo_sha,
        body,
    )
    full = f"{front}\n{body.strip()}\n"
    return GeneratedDocDraft(
        artifact_id=planned_doc.doc_id,
        category=planned_doc.category,
        title=planned_doc.title,
        slug_path=planned_doc.target_path,
        content_md=full,
        content_hash=sha256_text(full),
        source_files=source_files,
        source_lines=source_lines,
    )


def _front_matter(
    artifact_id: str,
    category: str,
    name: str,
    source_files: list[str],
    source_lines: dict[str, list[int | None]],
    generated_at: str,
    repo_sha: str,
    body: str,
) -> str:
    data = {
        "artifact_id": artifact_id,
        "category": category,
        "name": name,
        "source_files": source_files,
        "source_lines": source_lines,
        "generated_at": generated_at,
        "repo_sha": repo_sha,
        "content_hash": sha256_text(body),
    }
    lines = ["---"]
    for key, value in data.items():
        lines.append(f"{key}: {json.dumps(value)}")
    lines.append("---")
    return "\n".join(lines)
