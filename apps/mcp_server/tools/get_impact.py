"""Return PR-aware change impact + tiered doc diffs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from aura_backend.models import DocDiff, PrAnalysisRun

from ..server import mcp
from ._helpers import session_factory


@mcp.tool()
async def get_impact(pr_run_id: int, include_diff_text: bool = False) -> dict[str, Any]:
    """Return tier-bucketed impact summary + doc diffs for a PR analysis run.

    Set ``include_diff_text=True`` to embed each ``unified_diff`` text;
    otherwise diffs are returned as metadata-only (faster, smaller).
    """
    factory = session_factory()
    async with factory() as session:
        run = (
            await session.execute(
                select(PrAnalysisRun).where(PrAnalysisRun.id == pr_run_id)
            )
        ).scalars().first()
        if run is None:
            return {"error": "pr_run_not_found"}

        diffs = (
            await session.execute(select(DocDiff).where(DocDiff.pr_analysis_run_id == pr_run_id))
        ).scalars().all()

        diff_payload = []
        for d in diffs:
            row = {
                "artifact_id": d.artifact_id,
                "doc_path": d.doc_path,
                "change_type": d.change_type,
                "impact_tier": d.impact_tier,
                "affected_symbol_ids": d.affected_symbol_ids,
            }
            if include_diff_text:
                row["unified_diff"] = d.unified_diff
            diff_payload.append(row)

        impact = run.impact_summary or {}
        return {
            "pr_run_id": pr_run_id,
            "status": run.status,
            "tier_counts": impact.get("tier_counts", {}),
            "added": impact.get("added", []),
            "removed": impact.get("removed", []),
            "modified": impact.get("modified", []),
            "doc_diffs": diff_payload,
            "review_comment_body": run.review_comment_body,
        }
