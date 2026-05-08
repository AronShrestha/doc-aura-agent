"""PR Comment Agent.

Builds the body of the GitHub PR comment Aura posts on every pull
request. The single comment combines two sections under one stable
marker so subsequent webhooks update in place rather than spamming new
comments:

    <!-- aura-pr-review -->
    ## Summary  (always present)
    ...
    ---
    ## ⚠️ Mismatch warnings  (only when ``mismatch_flags['any']``)
    ...
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .clients import TextModelClient
from .parsing import markdown_from_text


logger = logging.getLogger(__name__)


MARKER = "<!-- aura-pr-review -->"


def build_summary_comment(
    impact: dict[str, Any],
    doc_diffs: list[dict[str, Any]],
    dashboard_url: str,
) -> str:
    counts = impact.get("tier_counts") or {}
    direct = [a for a in (impact.get("modified") or []) + (impact.get("added") or []) + (impact.get("removed") or [])][:3]
    direct_lines: list[str] = []
    for art in direct:
        loc = (
            f"{art.get('source_file')}:L{art.get('source_line_start')}"
            if art.get("source_file")
            else art.get("name", "?")
        )
        direct_lines.append(f"  - `{art.get('name', '?')}` ({art.get('category', '?')}) — {loc}")

    lines = [
        "## 📚 Aura Change Impact",
        "",
        f"**{counts.get('Direct', 0)} Direct · {counts.get('High', 0)} High · {counts.get('Medium', 0)} Medium**",
        f"📝 {len(doc_diffs)} doc diff{'' if len(doc_diffs) == 1 else 's'} generated",
        "",
        f"🔎 **[Open in Aura dashboard]({dashboard_url})**",
        "",
        "### Top changes",
    ]
    if direct_lines:
        lines.extend(direct_lines)
    else:
        lines.append("  _(no artifact-level changes)_")
    lines += [
        "",
        "### Artifact changes",
        f"- Added: {len(impact.get('added') or [])}",
        f"- Modified: {len(impact.get('modified') or [])}",
        f"- Removed: {len(impact.get('removed') or [])}",
    ]
    return "\n".join(lines)


def build_mismatch_comment(
    mismatch_flags: dict[str, Any],
    doc_diffs: list[dict[str, Any]],
    dashboard_url: str,
) -> str:
    if not mismatch_flags.get("any"):
        return ""
    lines = ["## ⚠️ Documentation mismatch", ""]
    new_endpoints = mismatch_flags.get("undocumented_endpoint") or []
    new_models = mismatch_flags.get("undocumented_data_model") or []
    direct_or_high = mismatch_flags.get("direct_or_high_doc_diff") or []

    if new_endpoints:
        lines.append("**Undocumented new endpoints:**")
        for art in new_endpoints[:5]:
            loc = (
                f"{art.get('source_file')}:L{art.get('source_line_start')}"
                if art.get("source_file")
                else ""
            )
            lines.append(f"- `{art.get('name','?')}` {('— ' + loc) if loc else ''}")
        lines.append("")
    if new_models:
        lines.append("**Undocumented new data models:**")
        for art in new_models[:5]:
            loc = (
                f"{art.get('source_file')}:L{art.get('source_line_start')}"
                if art.get("source_file")
                else ""
            )
            lines.append(f"- `{art.get('name','?')}` {('— ' + loc) if loc else ''}")
        lines.append("")
    if direct_or_high:
        lines.append(f"**{len(direct_or_high)} doc diff(s) at Direct/High impact:**")
        for d in direct_or_high[:5]:
            artifact_id = d.get("artifact_id", "")
            link = f"{dashboard_url}?diff={artifact_id}"
            lines.append(f"- [{d.get('doc_path','?')}]({link}) — {d.get('impact_tier','?')}")
        lines.append("")
    lines.append(f"🔎 **[Review in Aura dashboard]({dashboard_url})**")
    return "\n".join(lines)


def assemble_comment(summary: str, mismatch: str) -> str:
    parts = [MARKER, summary]
    if mismatch:
        parts += ["", "---", "", mismatch]
    return "\n".join(parts)


async def maybe_rewrite_with_llm(
    llm: TextModelClient | None,
    body: str,
    *,
    impact: dict[str, Any],
    mismatch_flags: dict[str, Any],
) -> str:
    if llm is None:
        return body
    logger.info("pr reviewer llm rewrite started", extra={"agent": "pr_reviewer"})
    messages = [
        {
            "role": "system",
            "content": (
                "You are Aura's PR Reviewer. Rewrite the provided Markdown comment to be friendlier and "
                f"more concise without losing any link, list item, or fact. Keep the leading marker `{MARKER}` "
                "intact at the top. Output Markdown only."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"body": body, "impact": impact, "mismatch_flags": mismatch_flags},
                sort_keys=True,
            ),
        },
    ]
    try:
        rewritten = markdown_from_text(await llm.complete(messages, temperature=0.1))
        if MARKER in rewritten:
            return rewritten
    except Exception as exc:
        logger.warning("pr reviewer llm rewrite failed", extra={"error": str(exc)})
    return body
