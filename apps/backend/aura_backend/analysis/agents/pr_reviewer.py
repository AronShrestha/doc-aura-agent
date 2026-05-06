from __future__ import annotations

import json
import logging
from typing import Any

from .clients import TextModelClient
from .parsing import markdown_from_text


logger = logging.getLogger(__name__)


async def run_pr_reviewer_agent(llm: TextModelClient, impact_summary: dict[str, Any], doc_diffs: list[dict[str, Any]]) -> str:
    logger.info("pr reviewer started", extra={"agent": "pr_reviewer"})
    messages = [
        {
            "role": "system",
            "content": (
                "You are Aura's PR Reviewer Agent. Produce a concise Markdown PR review comment from impact summary "
                "and documentation diffs. Include the stable marker <!-- aura-pr-review --> at the top."
            ),
        },
        {"role": "user", "content": json.dumps({"impact_summary": impact_summary, "doc_diffs": doc_diffs[:20]}, sort_keys=True)},
    ]
    body = markdown_from_text(await llm.complete(messages, temperature=0.1))
    logger.info("pr reviewer succeeded", extra={"agent": "pr_reviewer"})
    return body
