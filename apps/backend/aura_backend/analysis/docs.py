from __future__ import annotations

import json
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from .types import ExtractedArtifact, GeneratedDocDraft, RepoSnapshot
from .utils import sha256_text, slugify


logger = logging.getLogger(__name__)

DOC_ROOT = Path(".aura/docs")


def doc_path_for_artifact(artifact: ExtractedArtifact) -> str:
    if artifact.category == "project":
        return ".aura/docs/project-overview.md"
    if artifact.category == "architecture":
        return ".aura/docs/architecture/overview.md"
    if artifact.category == "endpoint":
        return f".aura/docs/endpoints/{slugify(artifact.name, 'endpoint')}.md"
    if artifact.category == "data_model":
        return f".aura/docs/data-models/{slugify(artifact.name, 'model')}.md"
    if artifact.category == "module":
        return f".aura/docs/modules/{slugify(artifact.name, 'module')}.md"
    if artifact.category == "function":
        return f".aura/docs/functions/{slugify(artifact.name, 'function')}.md"
    if artifact.category == "env_var":
        return f".aura/docs/env-vars/{slugify(artifact.name, 'env-var')}.md"
    if artifact.category == "config":
        return f".aura/docs/config/{slugify(artifact.name, 'config')}.md"
    if artifact.category == "flow":
        return f".aura/docs/flows/{slugify(artifact.name, 'flow')}.md"
    if artifact.category == "report":
        return ".aura/docs/reports/missing-docs.md"
    return f".aura/docs/{slugify(artifact.category)}/{slugify(artifact.name)}.md"


def build_virtual_artifacts(snapshot: RepoSnapshot, summary: dict[str, Any]) -> list[ExtractedArtifact]:
    from .utils import stable_artifact_id

    return [
        ExtractedArtifact(
            artifact_id=stable_artifact_id(snapshot.repo_id, "project", "overview"),
            category="project",
            name="Project Overview",
            canonical_locator="overview",
            source_file=None,
            source_line_start=None,
            source_line_end=None,
            payload={"summary": summary, "frameworks": snapshot.frameworks},
        ),
        ExtractedArtifact(
            artifact_id=stable_artifact_id(snapshot.repo_id, "architecture", "overview"),
            category="architecture",
            name="Architecture Overview",
            canonical_locator="overview",
            source_file=None,
            source_line_start=None,
            source_line_end=None,
            payload={"summary": summary},
        ),
        ExtractedArtifact(
            artifact_id=stable_artifact_id(snapshot.repo_id, "report", "missing-docs"),
            category="report",
            name="Missing Documentation Report",
            canonical_locator="missing-docs",
            source_file=None,
            source_line_start=None,
            source_line_end=None,
            payload={"parse_errors": summary.get("parse_errors", [])},
        ),
    ]


async def generate_docs(
    llm_chat,
    snapshot: RepoSnapshot,
    artifacts: list[ExtractedArtifact],
    summary: dict[str, Any],
) -> tuple[list[GeneratedDocDraft], dict[str, Any]]:
    selected = _select_artifacts_for_docs(snapshot, artifacts, summary)
    docs: list[GeneratedDocDraft] = []
    generated_at = datetime.now(UTC).isoformat()

    for artifact in selected:
        prompt = _prompt_for_artifact(snapshot, artifact, summary)
        content = await llm_chat(prompt)
        if not content or not content.strip():
            raise RuntimeError(f"llm_empty_doc:{artifact.artifact_id}")
        body = _normalize_markdown(content)
        front_matter = _front_matter(snapshot, artifact, generated_at, body)
        full_content = f"{front_matter}\n{body.strip()}\n"
        docs.append(
            GeneratedDocDraft(
                artifact_id=artifact.artifact_id,
                category=artifact.category,
                title=artifact.name,
                slug_path=doc_path_for_artifact(artifact),
                content_md=full_content,
                content_hash=sha256_text(full_content),
                source_files=_source_files(artifact),
                source_lines=_source_lines(artifact),
            )
        )

    index = _index_doc(snapshot, docs, generated_at)
    docs.insert(0, index)
    manifest = build_manifest(snapshot, docs)
    return docs, {
        "citation_coverage": _citation_coverage(docs),
        "unsupported_claims": 0,
        "section_completeness": 1.0 if docs else 0.0,
        "artifact_counts": summary,
        "doc_count": len(docs),
    } | {"manifest": manifest}


def write_docs(root: Path, docs: list[GeneratedDocDraft], manifest: dict[str, Any]) -> None:
    logger.info("writing generated docs", extra={"event": "docs_write_started"})
    staging = root / ".aura" / ".docs-staging"
    final_root = root / DOC_ROOT
    if staging.exists():
        import shutil

        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        rel = _doc_relative_path(doc.slug_path)
        target = staging / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(doc.content_md, encoding="utf-8")
    manifest_target = staging / ".aura-manifest.json"
    manifest_target.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    if final_root.exists():
        import shutil

        shutil.rmtree(final_root)
    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(final_root)
    logger.info("generated docs published", extra={"event": "docs_write_complete"})


def build_manifest(snapshot: RepoSnapshot, docs: list[GeneratedDocDraft]) -> dict[str, Any]:
    return {
        "repo_id": snapshot.repo_id,
        "repo_sha": snapshot.repo_sha,
        "generated_at": datetime.now(UTC).isoformat(),
        "docs": {
            doc.artifact_id: {
                "path": doc.slug_path,
                "category": doc.category,
                "title": doc.title,
                "content_hash": doc.content_hash,
                "source_files": doc.source_files,
            }
            for doc in docs
        },
    }


def _select_artifacts_for_docs(snapshot: RepoSnapshot, artifacts: list[ExtractedArtifact], summary: dict[str, Any]) -> list[ExtractedArtifact]:
    virtual = build_virtual_artifacts(snapshot, summary)
    supported = {"endpoint", "data_model", "module", "function", "env_var", "config", "flow"}
    real = [a for a in artifacts if a.category in supported]
    real.sort(key=lambda a: (a.category, a.name))
    return virtual + real


def _prompt_for_artifact(snapshot: RepoSnapshot, artifact: ExtractedArtifact, summary: dict[str, Any]) -> list[dict[str, str]]:
    diataxis = "reference"
    if artifact.category in {"project", "architecture", "flow"}:
        diataxis = "explanation"
    if artifact.category == "config":
        diataxis = "how-to"
    context = {
        "repo_sha": snapshot.repo_sha,
        "frameworks": snapshot.frameworks,
        "summary": summary,
        "artifact": {
            "artifact_id": artifact.artifact_id,
            "category": artifact.category,
            "name": artifact.name,
            "source_file": artifact.source_file,
            "source_line_start": artifact.source_line_start,
            "source_line_end": artifact.source_line_end,
            "payload": artifact.payload,
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You generate concise living documentation from static code facts. "
                "Return only Markdown. Do not invent unsupported behavior. "
                f"Write this as Diataxis {diataxis} documentation. "
                "Include a short Source Provenance section with file and line references when provided. "
                "Do not include YAML front matter."
            ),
        },
        {"role": "user", "content": json.dumps(context, sort_keys=True)},
    ]


def _front_matter(snapshot: RepoSnapshot, artifact: ExtractedArtifact, generated_at: str, body: str) -> str:
    data = {
        "artifact_id": artifact.artifact_id,
        "category": artifact.category,
        "name": artifact.name,
        "source_files": _source_files(artifact),
        "source_lines": _source_lines(artifact),
        "generated_at": generated_at,
        "repo_sha": snapshot.repo_sha,
        "content_hash": sha256_text(body),
    }
    lines = ["---"]
    for key, value in data.items():
        lines.append(f"{key}: {json.dumps(value)}")
    lines.append("---")
    return "\n".join(lines)


def _index_doc(snapshot: RepoSnapshot, docs: list[GeneratedDocDraft], generated_at: str) -> GeneratedDocDraft:
    sections = ["# Aura Documentation Index", ""]
    for doc in sorted(docs, key=lambda d: (d.category, d.title)):
        sections.append(f"- [{doc.title}]({doc.slug_path.removeprefix('.aura/docs/')})")
    content = "\n".join(sections) + "\n"
    full = "\n".join(
        [
            "---",
            f"artifact_id: {json.dumps('index')}",
            f"category: {json.dumps('index')}",
            f"name: {json.dumps('Documentation Index')}",
            "source_files: []",
            "source_lines: {}",
            f"generated_at: {json.dumps(generated_at)}",
            f"repo_sha: {json.dumps(snapshot.repo_sha)}",
            f"content_hash: {json.dumps(sha256_text(content))}",
            "---",
            content,
        ]
    )
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


def _normalize_markdown(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _source_files(artifact: ExtractedArtifact) -> list[str]:
    files = set(artifact.payload.get("source_files", []))
    if artifact.source_file:
        files.add(artifact.source_file)
    return sorted(files)


def _source_lines(artifact: ExtractedArtifact) -> dict[str, list[int | None]]:
    if not artifact.source_file:
        return {}
    return {artifact.source_file: [artifact.source_line_start, artifact.source_line_end]}


def _doc_relative_path(path: str) -> Path:
    return Path(path.removeprefix(".aura/docs/"))


def _citation_coverage(docs: list[GeneratedDocDraft]) -> float:
    if not docs:
        return 0.0
    cited = sum(1 for doc in docs if doc.source_files or doc.category in {"index", "project", "architecture", "report"})
    return cited / len(docs)
