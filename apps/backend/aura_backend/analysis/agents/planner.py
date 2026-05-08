"""Project-level documentation planner.

One LLM round-trip that classifies the codebase and chooses which doc
types to emit. Inputs: snapshot, summary, repo_analysis (architecture
summary), and project aggregations. Output: `DocumentationPlan` with a
`CodebaseProfile` and a list of `PlannedDoc` entries — one per chosen
doc-type-id (registered or `extra:<slug>`).

Always-on doc types whose applicability evaluates true MUST appear in
the final plan; the LLM may add `extra:<slug>` entries for codebase-
specific concerns the registry does not cover. Unknown ids without the
`extra:` prefix are rejected.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from .clients import TextModelClient
from .models import CodebaseProfile, DocumentationPlan, PlannedDoc, VisualContext
from .parsing import json_from_text
from ..aggregators import ProjectAggregations
from ..doc_types import (
    DOC_TYPE_REGISTRY,
    DocTypeSpec,
    applicable_doc_types,
    get_spec,
    make_extra_spec,
    required_doc_type_ids,
)
from ..types import RepoSnapshot
from ..utils import slugify, stable_artifact_id


logger = logging.getLogger(__name__)


async def run_project_doc_planner_agent(
    llm: TextModelClient,
    snapshot: RepoSnapshot,
    summary: dict[str, Any],
    aggs: ProjectAggregations,
    repo_analysis: dict[str, Any],
    visual_context: list[VisualContext],
) -> tuple[DocumentationPlan, dict[str, DocTypeSpec]]:
    """Plan project-level docs.

    Returns ``(plan, spec_by_doc_type_id)`` so the writer stage can look up
    the spec for both registered doc types and runtime ``extra:`` specs.
    """
    logger.info("project doc planner started", extra={"repo_id": snapshot.repo_id, "agent": "doc_planner"})
    applicable = applicable_doc_types(snapshot, summary, aggs)
    required_ids = set(required_doc_type_ids(snapshot, summary, aggs))
    menu = _doc_type_menu(applicable)
    signals = _aggregation_signals(aggs)

    messages = [
        {
            "role": "system",
            "content": (
                "You are Aura's Project Doc Planner. In ONE pass, classify "
                "the codebase and choose which project-level documentation to "
                "emit. Return strict JSON with keys: codebase_profile, "
                "doc_plan, rationale.\n\n"
                "codebase_profile = {type, primary_language, summary, "
                "subprojects:[{path,type}]} where type is one of "
                "'monorepo|webapp|api|library|cli|mobile|ml|iac|hybrid'.\n\n"
                "doc_plan = list of {doc_type_id,title,rationale}. For "
                "registered ids use the menu. For codebase-specific extras "
                "use doc_type_id starting with 'extra:' and ALSO include: "
                "diataxis ('explanation|reference|how-to|tutorial'), "
                "target_path (under '.aura/docs/extra/'), required_aggregations "
                "(list of aggregation field names from signals).\n\n"
                "Rules:\n"
                "- Every applicable always-on id MUST appear in doc_plan.\n"
                "- Do not propose ids that are not in the menu unless prefixed 'extra:'.\n"
                "- Skip non-applicable ids (their applies=false signals not enough data).\n"
                "- Prefer fewer high-quality extras over many shallow ones."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "repo_sha": snapshot.repo_sha,
                    "summary": summary,
                    "frameworks": snapshot.frameworks,
                    "repo_analysis": repo_analysis,
                    "aggregation_signals": signals,
                    "doc_type_menu": menu,
                    "required_doc_type_ids": sorted(required_ids),
                    "visual_context_count": len(visual_context),
                },
                sort_keys=True,
            ),
        },
    ]
    raw = await llm.complete(messages, temperature=0.1)
    data = json_from_text(raw)

    profile = _profile_from_json(data.get("codebase_profile") or {})
    plan_items = data.get("doc_plan") or []
    docs, spec_by_id = _materialize_plan(snapshot, plan_items)
    docs, spec_by_id = _ensure_minimum(snapshot, summary, aggs, docs, spec_by_id, required_ids)
    plan = DocumentationPlan(
        docs=sorted(docs, key=lambda d: (-d.priority, d.target_path)),
        rationale=str(data.get("rationale", "")),
        codebase_profile=profile,
    )
    logger.info(
        "project doc planner succeeded",
        extra={
            "repo_id": snapshot.repo_id,
            "agent": "doc_planner",
            "doc_count": len(plan.docs),
            "extras": sum(1 for d in plan.docs if d.doc_type_id.startswith("extra:")),
        },
    )
    return plan, spec_by_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc_type_menu(applicable: list[DocTypeSpec]) -> list[dict[str, Any]]:
    applicable_ids = {s.id for s in applicable}
    return [
        {
            "doc_type_id": spec.id,
            "title": spec.title,
            "diataxis": spec.diataxis,
            "target_path": spec.output_path_template,
            "always_on": spec.always_on,
            "applies": spec.id in applicable_ids,
        }
        for spec in DOC_TYPE_REGISTRY.values()
    ]


def _aggregation_signals(aggs: ProjectAggregations) -> dict[str, int]:
    return {
        "endpoint_groups": len(aggs.endpoint_catalog),
        "endpoints": sum(len(g.endpoints) for g in aggs.endpoint_catalog),
        "modules": len(aggs.module_responsibility_map),
        "data_models": len(aggs.data_model_graph.models),
        "env_vars": len(aggs.env_var_inventory),
        "config_files": len(aggs.config_inventory),
        "external_integrations": len(aggs.external_integrations),
        "protected_endpoints": len(aggs.auth_security_view.protected_endpoints),
        "secret_env_vars": len(aggs.auth_security_view.secret_env_vars),
        "background_jobs": len(aggs.background_jobs_view),
        "workflows": len(aggs.workflow_traces),
        "frontend_pages": len(aggs.frontend_view.pages),
        "frontend_components": len(aggs.frontend_view.components),
        "frontend_state_stores": len(aggs.frontend_view.state_stores),
        "cli_commands": len(aggs.cli_view),
        "iac_resources": len(aggs.iac_view),
        "ml_model_files": len(aggs.ml_view.model_files),
    }


def _profile_from_json(data: dict[str, Any]) -> CodebaseProfile:
    return CodebaseProfile(
        type=str(data.get("type", "unknown")),
        primary_language=str(data.get("primary_language", "unknown")),
        summary=str(data.get("summary", "")),
        subprojects=list(data.get("subprojects") or []),
    )


def _materialize_plan(
    snapshot: RepoSnapshot,
    items: list[dict[str, Any]],
) -> tuple[list[PlannedDoc], dict[str, DocTypeSpec]]:
    docs: list[PlannedDoc] = []
    spec_by_id: dict[str, DocTypeSpec] = {}
    seen_ids: set[str] = set()

    for item in items:
        doc_type_id = str(item.get("doc_type_id") or "").strip()
        if not doc_type_id or doc_type_id in seen_ids:
            continue
        seen_ids.add(doc_type_id)

        if doc_type_id.startswith("extra:"):
            spec = _spec_from_extra_item(doc_type_id, item)
            if spec is None:
                continue
        else:
            spec = get_spec(doc_type_id)
            if spec is None:
                # Unknown id; skip rather than fail the whole plan
                continue

        title = str(item.get("title") or spec.title)
        target_path = str(item.get("target_path") or spec.output_path_template)
        rationale = str(item.get("rationale") or "")
        docs.append(_planned_doc(snapshot, spec, title, target_path, rationale))
        spec_by_id[doc_type_id] = spec
    return docs, spec_by_id


def _spec_from_extra_item(doc_type_id: str, item: dict[str, Any]) -> DocTypeSpec | None:
    title = str(item.get("title") or "").strip()
    diataxis = str(item.get("diataxis") or "reference")
    target_path = str(item.get("target_path") or "").strip()
    required = item.get("required_aggregations") or []
    if not title or not target_path:
        return None
    if not target_path.startswith(".aura/docs/extra/"):
        target_path = f".aura/docs/extra/{slugify(doc_type_id.removeprefix('extra:'))}.md"
    if diataxis not in ("explanation", "reference", "how-to", "tutorial"):
        diataxis = "reference"
    try:
        return make_extra_spec(
            doc_type_id=doc_type_id,
            title=title,
            diataxis=diataxis,  # type: ignore[arg-type]
            target_path=target_path,
            required_aggregations=tuple(str(r) for r in required),
            task_brief=str(item.get("rationale") or "Document this codebase-specific concern."),
            body_outline=tuple(str(b) for b in (item.get("body_outline") or [])),
        )
    except ValueError:
        return None


def _planned_doc(
    snapshot: RepoSnapshot,
    spec: DocTypeSpec,
    title: str,
    target_path: str,
    rationale: str,
) -> PlannedDoc:
    doc_id = stable_artifact_id(snapshot.repo_id, "doc", spec.id)
    return PlannedDoc(
        doc_id=doc_id,
        title=title,
        category=_category_from_path(target_path),
        diataxis_type=spec.diataxis,
        target_path=target_path,
        doc_type_id=spec.id,
        required_aggregations=list(spec.required_aggregations),
        source_artifact_ids=[],
        uses_vlm_context=False,
        priority=100 if spec.always_on else 60,
        writer="project",
        rationale=rationale,
    )


def _category_from_path(target_path: str) -> str:
    rel = target_path.removeprefix(".aura/docs/").removesuffix(".md")
    head = rel.split("/", 1)[0] if "/" in rel else rel
    return head or "doc"


def _ensure_minimum(
    snapshot: RepoSnapshot,
    summary: dict[str, Any],
    aggs: ProjectAggregations,
    docs: list[PlannedDoc],
    spec_by_id: dict[str, DocTypeSpec],
    required_ids: set[str],
) -> tuple[list[PlannedDoc], dict[str, DocTypeSpec]]:
    have = {d.doc_type_id for d in docs}
    for req_id in sorted(required_ids):
        if req_id in have:
            continue
        spec = get_spec(req_id)
        if spec is None:
            continue
        docs.append(
            _planned_doc(
                snapshot,
                spec,
                spec.title,
                spec.output_path_template,
                rationale="Required Aura baseline documentation.",
            )
        )
        spec_by_id[req_id] = spec
    return docs, spec_by_id
