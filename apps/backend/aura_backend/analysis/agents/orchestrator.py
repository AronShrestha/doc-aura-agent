from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Any

from .clients import TextModelClient, VisionModelClient
from .context import compact_repo_context
from .models import VerificationReport
from .planner import run_doc_planner_agent
from .repo_analyst import run_repo_analyst_agent
from .verifier import run_verifier_agent
from .vlm_context import run_vlm_context_agent
from .writers import make_index_doc, run_artifact_writer_agent, run_system_writer_agent
from ..docs import build_manifest
from ..types import ExtractedArtifact, ExtractedEdge, GeneratedDocDraft, RepoSnapshot
from ...config import settings as _settings


logger = logging.getLogger(__name__)


async def run_documentation_agents(
    snapshot: RepoSnapshot,
    artifacts: list[ExtractedArtifact],
    edges: list[ExtractedEdge],
    summary: dict[str, Any],
    llm_client: TextModelClient,
    vlm_client: VisionModelClient | None = None,
    *,
    vlm_enabled: bool = False,
    max_artifacts: int = 120,
) -> tuple[list[GeneratedDocDraft], dict[str, Any]]:
    logger.info("agent workflow started", extra={"repo_id": snapshot.repo_id, "agent": "orchestrator"})
    visual_context = await run_vlm_context_agent(snapshot, vlm_client, vlm_enabled)
    logger.info("vlm context complete", extra={"repo_id": snapshot.repo_id, "agent": "vlm_context"})
    repo_context = compact_repo_context(snapshot, artifacts, edges, summary, max_artifacts=max_artifacts)
    repo_analysis = await run_repo_analyst_agent(llm_client, repo_context, visual_context)
    logger.info("repo analyst complete", extra={"repo_id": snapshot.repo_id, "agent": "repo_analyst"})
    plan = await run_doc_planner_agent(llm_client, snapshot, artifacts, repo_analysis, visual_context)
    logger.info("doc planner complete", extra={"repo_id": snapshot.repo_id, "agent": "doc_planner"})
    docs: list[GeneratedDocDraft] = []
    generated_at = datetime.now(UTC).isoformat()
    by_id = {artifact.artifact_id: artifact for artifact in artifacts}

    for planned in plan.docs:
        source_artifacts = [by_id[aid] for aid in planned.source_artifact_ids if aid in by_id]
        logger.info(
            "planned doc generation started",
            extra={"repo_id": snapshot.repo_id, "agent": planned.writer},
        )
        if planned.writer == "artifact":
            docs.append(await run_artifact_writer_agent(llm_client, snapshot, planned, source_artifacts, repo_analysis, visual_context, generated_at))
        else:
            docs.append(await run_system_writer_agent(llm_client, snapshot, planned, source_artifacts, repo_analysis, visual_context, generated_at))

    index = make_index_doc(snapshot, docs, generated_at)
    docs.insert(0, index)
    manifest = build_manifest(snapshot, docs)
    if _settings.verifier_enabled:
        verification = await run_verifier_agent(llm_client, snapshot, plan, docs, manifest)
        if not verification.passed:
            logger.warning("agent verification failed", extra={"repo_id": snapshot.repo_id, "agent": "verifier"})
            raise RuntimeError(f"agent_verification_failed:{'; '.join(verification.issues)}")
    else:
        logger.info("verifier disabled", extra={"repo_id": snapshot.repo_id, "agent": "verifier"})
        verification = VerificationReport(
            passed=True,
            citation_coverage=0.0,
            unsupported_claims=0,
            section_completeness=0.0,
            issues=["verifier_disabled"],
        )
    logger.info("agent workflow complete", extra={"repo_id": snapshot.repo_id, "agent": "orchestrator"})

    quality = _quality_report(summary, repo_analysis, plan, visual_context, verification, docs)
    quality["manifest"] = manifest
    return docs, quality


def _quality_report(
    summary: dict[str, Any],
    repo_analysis: dict[str, Any],
    plan,
    visual_context,
    verification: VerificationReport,
    docs: list[GeneratedDocDraft],
) -> dict[str, Any]:
    return {
        "citation_coverage": verification.citation_coverage,
        "unsupported_claims": verification.unsupported_claims,
        "section_completeness": verification.section_completeness,
        "artifact_counts": summary,
        "doc_count": len(docs),
        "agent_workflow": "deterministic_llm_vlm",
        "agents": ["vlm_context", "repo_analyst", "doc_planner", "artifact_writer", "system_writer", "verifier"],
        "planned_doc_count": len(plan.docs),
        "visual_context_count": len(visual_context),
        "repo_analysis": repo_analysis,
        "verification_issues": verification.issues,
    }
