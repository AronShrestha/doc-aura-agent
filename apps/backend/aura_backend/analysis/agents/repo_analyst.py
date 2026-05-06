from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from .clients import TextModelClient
from .models import VisualContext
from .parsing import json_from_text


logger = logging.getLogger(__name__)


async def run_repo_analyst_agent(llm: TextModelClient, repo_context: dict[str, Any], visual_context: list[VisualContext]) -> dict[str, Any]:
    logger.info("repo analyst started", extra={"agent": "repo_analyst"})
    messages = [
        {
            "role": "system",
            "content": (
                "You are Aura's Repo Analyst Agent. Analyze static repo facts only. "
                "Return JSON with keys: architecture_summary, frameworks, risk_areas, artifact_groups, "
                "human_docs_summary, media_assets_summary, documentation_opportunities. "
                "Do not invent runtime behavior."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "repo_context": repo_context,
                    "visual_context": [asdict(v) for v in visual_context],
                },
                sort_keys=True,
            ),
        },
    ]
    raw = await llm.complete(messages, temperature=0.1)
    data = json_from_text(raw)
    required = ["architecture_summary", "frameworks", "risk_areas", "artifact_groups", "documentation_opportunities"]
    missing = [key for key in required if key not in data]
    if missing:
        raise RuntimeError(f"repo_analyst_missing_keys:{','.join(missing)}")
    logger.info("repo analyst succeeded", extra={"agent": "repo_analyst"})
    return data
