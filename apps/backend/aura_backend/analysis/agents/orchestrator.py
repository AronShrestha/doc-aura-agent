from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import datetime, UTC
from typing import Any, Awaitable, Callable

from .clients import TextModelClient, VisionModelClient
from .context import compact_repo_context
from .models import PlannedDoc, VerificationReport
from .narrator import run_narrator_agent
from .planner import run_project_doc_planner_agent
from .repo_analyst import run_repo_analyst_agent
from .verifier import run_verifier_agent
from .vlm_context import run_vlm_context_agent
from .writers import make_coverage_doc, make_index_doc, run_project_doc_writer
from ..aggregators import ProjectAggregations, build_project_aggregations
from ..doc_types import expand_extensible_plan, get_spec
from ..docs import build_manifest
from ..types import ExtractedArtifact, ExtractedEdge, GeneratedDocDraft, RepoSnapshot
from ..utils import stable_artifact_id
from ...config import settings as _settings


logger = logging.getLogger(__name__)


ProgressCallback = Callable[[str, int, dict[str, Any] | None], Awaitable[None]]


# Synthesize stage spans 40 → 88 in pipeline.STAGES; sub-progress lives here.
_PROG_AGGREGATE = 44
_PROG_VLM = 48
_PROG_ANALYST = 54
_PROG_PLAN = 60
_PROG_COMPOSE_START = 60
_PROG_COMPOSE_END = 84
_PROG_VERIFY = 87


async def _emit(progress_cb: ProgressCallback | None, stage: str, pct: int, **extra: Any) -> None:
    logger.info(
        "doc generation progress",
        extra={"stage": stage, "progress": pct, **extra},
    )
    if progress_cb is not None:
        await progress_cb(stage, pct, dict(extra) or None)


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
    progress_cb: ProgressCallback | None = None,
) -> tuple[list[GeneratedDocDraft], dict[str, Any]]:
    logger.info("agent workflow started", extra={"repo_id": snapshot.repo_id, "agent": "orchestrator"})

    # ---- aggregate -----------------------------------------------------
    aggs = build_project_aggregations(snapshot, artifacts, edges, summary)
    await _emit(
        progress_cb,
        "aggregate",
        _PROG_AGGREGATE,
        repo_id=snapshot.repo_id,
        endpoints=sum(len(g.endpoints) for g in aggs.endpoint_catalog),
        data_models=len(aggs.data_model_graph.models),
        env_vars=len(aggs.env_var_inventory),
    )

    # ---- analyst (architecture summary) ---------------------------------
    visual_context = await run_vlm_context_agent(snapshot, vlm_client, vlm_enabled)
    await _emit(progress_cb, "vlm_context", _PROG_VLM, repo_id=snapshot.repo_id, vlm_count=len(visual_context))
    repo_context = compact_repo_context(snapshot, artifacts, edges, summary, max_artifacts=max_artifacts)
    repo_analysis = await run_repo_analyst_agent(llm_client, repo_context, visual_context)
    await _emit(progress_cb, "analyst", _PROG_ANALYST, repo_id=snapshot.repo_id)

    # ---- plan (single-pass codebase profile + doc plan) -----------------
    plan, spec_by_id = await run_project_doc_planner_agent(
        llm_client, snapshot, summary, aggs, repo_analysis, visual_context
    )
    await _emit(
        progress_cb,
        "plan",
        _PROG_PLAN,
        repo_id=snapshot.repo_id,
        planned_doc_count=len(plan.docs),
        codebase_type=plan.codebase_profile.type if plan.codebase_profile else None,
    )

    # ---- expand extensible specs into per-entity PlannedDocs -------------
    extensible_planned = _expand_extensible(snapshot, summary, aggs, spec_by_id)
    plan.docs.extend(extensible_planned)
    plan.docs.sort(key=lambda d: (-d.priority, d.target_path))

    # ---- narrator (one extra LLM call producing context-aware status lines) -
    narration_lines: list[str] = []
    if _settings.narrator_enabled:
        try:
            narration_lines = await run_narrator_agent(
                llm_client, snapshot, plan, aggs, repo_analysis
            )
        except Exception as exc:
            logger.warning(
                "narrator agent failed; continuing without narration",
                extra={"event": "narrator_failed", "error": str(exc)},
            )
            narration_lines = []

    # ---- compose (parallel, bounded by semaphore) -----------------------
    human_docs = [a for a in artifacts if a.category == "human_doc"]
    generated_at = datetime.now(UTC).isoformat()
    composable = [
        p for p in plan.docs
        if p.doc_type_id in spec_by_id and p.doc_type_id != "coverage-report"
    ]
    total = max(1, len(composable))
    span = _PROG_COMPOSE_END - _PROG_COMPOSE_START
    concurrency = max(1, int(getattr(_settings, "llm_max_concurrency", 4)))
    sem = asyncio.Semaphore(concurrency)
    completed = 0
    narration_idx = 0
    narration_step = max(1, total // max(1, len(narration_lines))) if narration_lines else 0

    async def _one(planned: PlannedDoc) -> GeneratedDocDraft | None:
        nonlocal completed, narration_idx
        spec = spec_by_id.get(planned.doc_type_id)
        if spec is None:
            logger.warning(
                "skipping doc with unknown spec",
                extra={"repo_id": snapshot.repo_id, "doc_type_id": planned.doc_type_id},
            )
            return None
        try:
            async with sem:
                draft = await run_project_doc_writer(
                    llm_client,
                    snapshot,
                    planned,
                    spec,
                    aggs,
                    repo_analysis,
                    visual_context,
                    generated_at,
                    human_docs=human_docs,
                )
        except Exception as exc:
            # One doc failing must not abort the whole pipeline. Log and
            # skip; verifier later flags coverage gaps.
            logger.warning(
                "doc writer failed; skipping doc",
                extra={
                    "event": "doc_writer_failed",
                    "repo_id": snapshot.repo_id,
                    "doc_type_id": spec.id,
                    "slug_path": planned.target_path,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            draft = None
        completed += 1
        pct = _PROG_COMPOSE_START + int(completed / total * span)
        narration: str | None = None
        if narration_lines and narration_step and completed % narration_step == 0 and narration_idx < len(narration_lines):
            narration = narration_lines[narration_idx]
            narration_idx += 1
        await _emit(
            progress_cb,
            "compose",
            pct,
            repo_id=snapshot.repo_id,
            doc_type_id=spec.id,
            doc=f"{completed}/{total}",
            slug_path=planned.target_path,
            narration=narration,
        )
        return draft

    results = await asyncio.gather(*[_one(p) for p in composable], return_exceptions=False)
    docs: list[GeneratedDocDraft] = [d for d in results if d is not None]
    failed = sum(1 for r in results if r is None)
    if failed:
        logger.warning(
            "compose finished with failures",
            extra={"event": "compose_partial", "failed": failed, "total": len(results)},
        )

    # Drain any narration lines we didn't place yet (paced rounding leftover).
    while narration_idx < len(narration_lines):
        await _emit(
            progress_cb,
            "compose",
            _PROG_COMPOSE_END,
            repo_id=snapshot.repo_id,
            narration=narration_lines[narration_idx],
        )
        narration_idx += 1

    # ---- post-hoc deterministic docs (no LLM) ---------------------------
    coverage = make_coverage_doc(snapshot, aggs, docs, generated_at)
    docs.append(coverage)
    index = make_index_doc(snapshot, docs, generated_at)
    docs.insert(0, index)

    # ---- persist (manifest) ---------------------------------------------
    profile_dict = asdict(plan.codebase_profile) if plan.codebase_profile else {}
    manifest = build_manifest(snapshot, docs, codebase_profile=profile_dict)

    # ---- verify ----------------------------------------------------------
    if _settings.verifier_enabled:
        verification = await run_verifier_agent(
            llm_client, snapshot, plan, docs, manifest, aggs=aggs
        )
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
    await _emit(progress_cb, "verify", _PROG_VERIFY, repo_id=snapshot.repo_id, passed=verification.passed)

    logger.info("agent workflow complete", extra={"repo_id": snapshot.repo_id, "agent": "orchestrator"})
    quality = _quality_report(summary, repo_analysis, plan, visual_context, verification, docs, aggs)
    quality["manifest"] = manifest
    return docs, quality


def _expand_extensible(
    snapshot: RepoSnapshot,
    summary: dict[str, Any],
    aggs: ProjectAggregations,
    spec_by_id: dict[str, Any],
) -> list[PlannedDoc]:
    """Materialize one PlannedDoc per per-entity instance + register the spec."""
    out: list[PlannedDoc] = []
    seen_paths: set[str] = set()
    for item in expand_extensible_plan(snapshot, summary, aggs):
        spec = get_spec(item["doc_type_id"])
        if spec is None:
            continue
        target_path = item["target_path"]
        if target_path in seen_paths:
            continue
        seen_paths.add(target_path)
        spec_by_id[item["doc_type_id"]] = spec  # ensure writer can look it up
        # Distinct doc_id per entity so persistence doesn't collide.
        doc_id = stable_artifact_id(snapshot.repo_id, "doc", f"{item['doc_type_id']}::{target_path}")
        out.append(
            PlannedDoc(
                doc_id=doc_id,
                title=item["title"],
                category=spec.id.split("-", 1)[0],
                diataxis_type=spec.diataxis,
                target_path=target_path,
                doc_type_id=spec.id,
                required_aggregations=list(spec.required_aggregations),
                source_artifact_ids=[],
                uses_vlm_context=False,
                priority=item.get("priority", 50),
                writer="project",
                rationale="auto-expanded per entity",
                entity_focus=item["entity_focus"],
            )
        )
    return out


def _quality_report(
    summary: dict[str, Any],
    repo_analysis: dict[str, Any],
    plan,
    visual_context,
    verification: VerificationReport,
    docs: list[GeneratedDocDraft],
    aggs: ProjectAggregations,
) -> dict[str, Any]:
    profile = asdict(plan.codebase_profile) if plan.codebase_profile else {}
    chosen = [
        {"doc_type_id": d.doc_type_id, "target_path": d.target_path, "priority": d.priority}
        for d in plan.docs
    ]
    return {
        "citation_coverage": verification.citation_coverage,
        "unsupported_claims": verification.unsupported_claims,
        "section_completeness": verification.section_completeness,
        "artifact_counts": summary,
        "doc_count": len(docs),
        "agent_workflow": "project_doc_v2",
        "agents": ["vlm_context", "repo_analyst", "project_doc_planner", "project_doc_writer", "verifier"],
        "planned_doc_count": len(plan.docs),
        "visual_context_count": len(visual_context),
        "repo_analysis": repo_analysis,
        "verification_issues": verification.issues,
        "codebase_profile": profile,
        "chosen_doc_types": chosen,
        "aggregation_signals": {
            "endpoints": sum(len(g.endpoints) for g in aggs.endpoint_catalog),
            "data_models": len(aggs.data_model_graph.models),
            "env_vars": len(aggs.env_var_inventory),
            "modules": len(aggs.module_responsibility_map),
            "external_integrations": len(aggs.external_integrations),
            "background_jobs": len(aggs.background_jobs_view),
            "frontend_pages": len(aggs.frontend_view.pages),
            "frontend_components": len(aggs.frontend_view.components),
            "cli_commands": len(aggs.cli_view),
        },
    }
