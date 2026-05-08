from __future__ import annotations

import json
import logging
import re
from typing import Any

from .clients import TextModelClient
from .models import DocumentationPlan
from ..aggregators import ProjectAggregations
from ..types import RepoSnapshot


logger = logging.getLogger(__name__)


_SYSTEM = (
    "You are an engineering UI assistant that narrates a documentation generation pipeline "
    "while it runs. Output is shown live to the engineer who started the run, like a build log "
    "but readable. Each line is a single short status sentence (under 90 characters) describing "
    "what the agents are doing right now. Be specific to the codebase — mention real frameworks, "
    "concrete numbers, real route or model names. No filler, no marketing. Output strict JSON."
)


_USER_TEMPLATE = """Codebase profile:
{profile}

Aggregation signals:
- endpoints: {endpoints}
- data models: {data_models}
- env vars: {env_vars}
- modules: {modules}
- background jobs: {background_jobs}
- frontend pages: {frontend_pages}
- frontend components: {frontend_components}

Sample endpoints (path :: method):
{endpoint_sample}

Sample data models:
{model_sample}

Planned documents ({planned_count}):
{planned_sample}

Architecture summary (excerpt):
{arch_excerpt}

Produce 6-10 narration lines an engineer would want to read while their docs generate.
Examples of good lines:
- "FastAPI project — 14 routes detected"
- "Reading models.py — 9 SQLAlchemy entities"
- "Drafting endpoints reference — POST /repos/analyze, GET /runs/:id"
- "Reviewer agent will diff this on the next PR merge"

Bad examples (do not produce):
- "Working on docs..." (too vague)
- "Hi! I am an AI assistant..." (preamble)
- "Successfully completed" (we're still running)

Respond with strict JSON: {{"lines": ["...", "..."]}}.
"""


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


async def run_narrator_agent(
    llm: TextModelClient,
    snapshot: RepoSnapshot,
    plan: DocumentationPlan,
    aggs: ProjectAggregations,
    repo_analysis: dict[str, Any],
) -> list[str]:
    profile = ""
    if plan.codebase_profile is not None:
        profile = (
            f"type={plan.codebase_profile.type} "
            f"primary_language={plan.codebase_profile.primary_language} "
            f"summary={_truncate(plan.codebase_profile.summary or '', 240)}"
        )

    endpoint_sample = "\n".join(
        f"- {ep.method} {ep.path}"
        for group in (aggs.endpoint_catalog or [])[:1]
        for ep in (group.endpoints or [])[:6]
    ) or "(none)"

    model_sample = "\n".join(
        f"- {m.name}"
        for m in (aggs.data_model_graph.models or [])[:6]
    ) or "(none)"

    planned_sample = "\n".join(
        f"- {d.title} ({d.target_path})"
        for d in plan.docs[:8]
    ) or "(none)"

    arch_excerpt = ""
    if isinstance(repo_analysis, dict):
        for key in ("architecture_summary", "summary", "overview"):
            val = repo_analysis.get(key)
            if isinstance(val, str) and val:
                arch_excerpt = _truncate(val, 800)
                break

    user_prompt = _USER_TEMPLATE.format(
        profile=profile or "(unknown)",
        endpoints=sum(len(g.endpoints) for g in aggs.endpoint_catalog),
        data_models=len(aggs.data_model_graph.models),
        env_vars=len(aggs.env_var_inventory),
        modules=len(aggs.module_responsibility_map),
        background_jobs=len(aggs.background_jobs_view),
        frontend_pages=len(aggs.frontend_view.pages),
        frontend_components=len(aggs.frontend_view.components),
        endpoint_sample=endpoint_sample,
        model_sample=model_sample,
        planned_count=len(plan.docs),
        planned_sample=planned_sample,
        arch_excerpt=arch_excerpt or "(none)",
    )

    raw = await llm.complete(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=512,
        temperature=0.4,
    )

    return _parse_lines(raw)


def _parse_lines(raw: str) -> list[str]:
    if not raw:
        return []
    text = raw.strip()
    # Strip code fences if present.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        obj = json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            logger.warning("narrator output not JSON", extra={"event": "narrator_parse_fail"})
            return []
        try:
            obj = json.loads(match.group(0))
        except Exception:
            logger.warning("narrator output not JSON (after extract)", extra={"event": "narrator_parse_fail"})
            return []

    lines = obj.get("lines") if isinstance(obj, dict) else None
    if not isinstance(lines, list):
        return []
    cleaned: list[str] = []
    for item in lines:
        if not isinstance(item, str):
            continue
        s = item.strip().strip("•-* ")
        if 6 <= len(s) <= 140:
            cleaned.append(s)
    return cleaned[:10]
