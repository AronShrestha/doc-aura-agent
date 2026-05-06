from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from .clients import TextModelClient
from .models import DocumentationPlan, PlannedDoc, VisualContext
from .parsing import json_from_text
from ..docs import doc_path_for_artifact
from ..types import ExtractedArtifact, RepoSnapshot
from ..utils import stable_artifact_id


logger = logging.getLogger(__name__)


async def run_doc_planner_agent(
    llm: TextModelClient,
    snapshot: RepoSnapshot,
    artifacts: list[ExtractedArtifact],
    repo_analysis: dict[str, Any],
    visual_context: list[VisualContext],
) -> DocumentationPlan:
    logger.info("doc planner started", extra={"repo_id": snapshot.repo_id, "agent": "doc_planner"})
    virtual_docs = _default_system_docs(snapshot)
    artifact_candidates = _artifact_candidates(artifacts)
    messages = [
        {
            "role": "system",
            "content": (
                "You are Aura's Doc Planner Agent. Choose the most useful living documentation for this repo. "
                "Return strict JSON with keys: rationale, docs. docs is an array of objects with keys: "
                "doc_id,title,category,diataxis_type,target_path,source_artifact_ids,uses_vlm_context,priority,writer,rationale. "
                "writer must be artifact or system. diataxis_type must be reference, explanation, or how-to. "
                "Prefer useful coverage over generating every artifact blindly."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "repo_sha": snapshot.repo_sha,
                    "frameworks": snapshot.frameworks,
                    "repo_analysis": repo_analysis,
                    "visual_context": [asdict(v) for v in visual_context],
                    "required_system_doc_options": virtual_docs,
                    "artifact_doc_candidates": artifact_candidates[:200],
                },
                sort_keys=True,
            ),
        },
    ]
    raw = await llm.complete(messages, temperature=0.1)
    data = json_from_text(raw)
    plan = _plan_from_json(data)
    plan = _ensure_minimum_plan(snapshot, artifacts, plan)
    logger.info("doc planner succeeded", extra={"repo_id": snapshot.repo_id, "agent": "doc_planner"})
    return plan


def _plan_from_json(data: dict[str, Any]) -> DocumentationPlan:
    docs = []
    for item in data.get("docs", []):
        docs.append(
            PlannedDoc(
                doc_id=str(item["doc_id"]),
                title=str(item["title"]),
                category=str(item["category"]),
                diataxis_type=item.get("diataxis_type", "reference"),
                target_path=str(item["target_path"]),
                source_artifact_ids=[str(v) for v in item.get("source_artifact_ids", [])],
                uses_vlm_context=bool(item.get("uses_vlm_context", False)),
                priority=int(item.get("priority", 50)),
                writer=item.get("writer", "system"),
                rationale=str(item.get("rationale", "")),
            )
        )
    if not docs:
        raise RuntimeError("doc_planner_returned_no_docs")
    return DocumentationPlan(docs=docs, rationale=str(data.get("rationale", "")))


def _ensure_minimum_plan(snapshot: RepoSnapshot, artifacts: list[ExtractedArtifact], plan: DocumentationPlan) -> DocumentationPlan:
    existing_paths = {doc.target_path for doc in plan.docs}
    required = _default_system_docs(snapshot)
    for doc in required:
        if doc["target_path"] not in existing_paths:
            plan.docs.append(
                PlannedDoc(
                    doc_id=doc["doc_id"],
                    title=doc["title"],
                    category=doc["category"],
                    diataxis_type=doc["diataxis_type"],
                    target_path=doc["target_path"],
                    writer="system",
                    priority=doc["priority"],
                    rationale="Required Aura baseline documentation.",
                )
            )
    for artifact in artifacts:
        if artifact.category in {"endpoint", "data_model", "config", "env_var"} and doc_path_for_artifact(artifact) not in existing_paths:
            plan.docs.append(
                PlannedDoc(
                    doc_id=artifact.artifact_id,
                    title=artifact.name,
                    category=artifact.category,
                    diataxis_type="reference" if artifact.category != "config" else "how-to",
                    target_path=doc_path_for_artifact(artifact),
                    source_artifact_ids=[artifact.artifact_id],
                    writer="artifact",
                    priority=70,
                    rationale="High-value artifact reference documentation.",
                )
            )
    plan.docs.sort(key=lambda d: (-d.priority, d.target_path))
    return plan


def _default_system_docs(snapshot: RepoSnapshot) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": stable_artifact_id(snapshot.repo_id, "project", "overview"),
            "title": "Project Overview",
            "category": "project",
            "diataxis_type": "explanation",
            "target_path": ".aura/docs/project-overview.md",
            "priority": 100,
        },
        {
            "doc_id": stable_artifact_id(snapshot.repo_id, "architecture", "overview"),
            "title": "Architecture Overview",
            "category": "architecture",
            "diataxis_type": "explanation",
            "target_path": ".aura/docs/architecture/overview.md",
            "priority": 95,
        },
        {
            "doc_id": stable_artifact_id(snapshot.repo_id, "report", "missing-docs"),
            "title": "Missing Documentation Report",
            "category": "report",
            "diataxis_type": "reference",
            "target_path": ".aura/docs/reports/missing-docs.md",
            "priority": 90,
        },
    ]


def _artifact_candidates(artifacts: list[ExtractedArtifact]) -> list[dict[str, Any]]:
    return [
        {
            "artifact_id": a.artifact_id,
            "category": a.category,
            "name": a.name,
            "target_path": doc_path_for_artifact(a),
            "source_file": a.source_file,
        }
        for a in sorted(artifacts, key=lambda item: (item.category, item.name))
        if a.category in {"endpoint", "data_model", "module", "function", "env_var", "config", "flow"}
    ]
