from __future__ import annotations

import difflib
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..models import AnalysisRun, Artifact, DocDiff, GeneratedDoc, PrAnalysisRun, PullRequest
from ..analysis.pipeline import run_static_analysis_for_ref


logger = logging.getLogger(__name__)


async def analyze_pull_request(
    session_factory: async_sessionmaker,
    pull_request_id: int,
) -> None:
    logger.info("pr analysis starting", extra={"pr_id": pull_request_id})
    async with session_factory() as session:
        pr = (await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))).scalar_one()
        pr_run = PrAnalysisRun(pull_request_id=pr.id, status="running")
        session.add(pr_run)
        await session.commit()
        pr_run_id = pr_run.id
    logger.info("pr analysis run created", extra={"pr_id": pull_request_id, "pr_run_id": pr_run_id})

    try:
        base_run_id = await run_static_analysis_for_ref(session_factory, pr.repo_id, pr.base_ref, pr.base_sha)
        head_run_id = await run_static_analysis_for_ref(session_factory, pr.repo_id, pr.head_ref, pr.head_sha)
        impact, diff_rows, comment = await _compare_runs(session_factory, base_run_id, head_run_id)
        logger.info("pr base/head runs compared", extra={"pr_id": pull_request_id, "pr_run_id": pr_run_id})
        async with session_factory() as session:
            pr_run = (await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.id == pr_run_id))).scalar_one()
            pr_run.status = "succeeded"
            pr_run.base_run_id = base_run_id
            pr_run.head_run_id = head_run_id
            pr_run.impact_summary = impact
            pr_run.review_comment_body = comment
            pr_run.updated_at = datetime.utcnow()
            session.add_all([_doc_diff_row(pr_run_id, row) for row in diff_rows])
            await session.commit()
        logger.info("pr analysis succeeded", extra={"pr_id": pull_request_id, "pr_run_id": pr_run_id})
    except Exception as exc:
        logger.exception("pr analysis failed", extra={"pr_id": pull_request_id, "pr_run_id": pr_run_id})
        async with session_factory() as session:
            pr_run = (await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.id == pr_run_id))).scalar_one()
            pr_run.status = "failed"
            pr_run.error = str(exc)
            pr_run.updated_at = datetime.utcnow()
            await session.commit()


async def _compare_runs(session_factory: async_sessionmaker, base_run_id: int, head_run_id: int) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    logger.info("comparing pr analysis runs", extra={"event": "pr_compare"})
    async with session_factory() as session:
        base_artifacts = (await session.execute(select(Artifact).where(Artifact.run_id == base_run_id))).scalars().all()
        head_artifacts = (await session.execute(select(Artifact).where(Artifact.run_id == head_run_id))).scalars().all()
        base_docs = (await session.execute(select(GeneratedDoc).where(GeneratedDoc.run_id == base_run_id))).scalars().all()
        head_docs = (await session.execute(select(GeneratedDoc).where(GeneratedDoc.run_id == head_run_id))).scalars().all()

    base_by_id = {a.artifact_id: a for a in base_artifacts}
    head_by_id = {a.artifact_id: a for a in head_artifacts}
    added = sorted(set(head_by_id) - set(base_by_id))
    removed = sorted(set(base_by_id) - set(head_by_id))
    modified = sorted(
        aid
        for aid in set(base_by_id) & set(head_by_id)
        if _artifact_fingerprint(base_by_id[aid]) != _artifact_fingerprint(head_by_id[aid])
    )
    unchanged = sorted((set(base_by_id) & set(head_by_id)) - set(modified))
    impacted = added + removed + modified
    severities = [_severity(head_by_id.get(aid) or base_by_id[aid], aid in removed) for aid in impacted]
    impact = {
        "added": [_artifact_summary(head_by_id[aid]) for aid in added],
        "removed": [_artifact_summary(base_by_id[aid]) for aid in removed],
        "modified": [_artifact_summary(head_by_id[aid]) for aid in modified],
        "unchanged_count": len(unchanged),
        "severity_counts": {level: severities.count(level) for level in ["critical", "warning", "info"]},
    }
    diffs = _doc_diffs(base_docs, head_docs)
    logger.info("pr impact comparison complete", extra={"event": "pr_compare_complete"})
    return impact, diffs, _comment_body(impact, diffs)


def _artifact_fingerprint(artifact: Artifact) -> str:
    payload = dict(artifact.payload or {})
    return str(
        {
            "name": artifact.name,
            "category": artifact.category,
            "source_file": artifact.source_file,
            "source_line_start": artifact.source_line_start,
            "source_line_end": artifact.source_line_end,
            "payload": payload,
        }
    )


def _artifact_summary(artifact: Artifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "category": artifact.category,
        "name": artifact.name,
        "source_file": artifact.source_file,
        "source_line_start": artifact.source_line_start,
        "source_line_end": artifact.source_line_end,
    }


def _severity(artifact: Artifact, removed: bool = False) -> str:
    if artifact.category == "endpoint":
        return "critical"
    if artifact.category == "data_model" and removed:
        return "critical"
    if artifact.category == "env_var" and artifact.payload.get("secret_like"):
        return "critical"
    if artifact.category in {"function", "module", "data_model", "config", "env_var"}:
        return "warning"
    return "info"


def _doc_diffs(base_docs: list[GeneratedDoc], head_docs: list[GeneratedDoc]) -> list[dict[str, Any]]:
    base_by_id = {d.artifact_id: d for d in base_docs}
    head_by_id = {d.artifact_id: d for d in head_docs}
    rows: list[dict[str, Any]] = []
    for aid in sorted(set(base_by_id) | set(head_by_id)):
        before = base_by_id.get(aid)
        after = head_by_id.get(aid)
        if before and after and before.content_hash == after.content_hash:
            continue
        before_text = before.content_md if before else ""
        after_text = after.content_md if after else ""
        change_type = "added" if before is None else "removed" if after is None else "modified"
        doc_path = (after or before).slug_path
        unified = "\n".join(
            difflib.unified_diff(
                before_text.splitlines(),
                after_text.splitlines(),
                fromfile=f"base/{doc_path}",
                tofile=f"head/{doc_path}",
                lineterm="",
            )
        )
        rows.append(
            {
                "artifact_id": aid,
                "doc_path": doc_path,
                "change_type": change_type,
                "unified_diff": unified,
                "side_by_side": _side_by_side(before_text, after_text),
            }
        )
    return rows


def _side_by_side(before: str, after: str) -> dict[str, Any]:
    matcher = difflib.SequenceMatcher(a=before.splitlines(), b=after.splitlines())
    rows = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        rows.append({"type": tag, "base": before.splitlines()[i1:i2], "head": after.splitlines()[j1:j2]})
    return {"rows": rows}


def _doc_diff_row(pr_run_id: int, row: dict[str, Any]) -> DocDiff:
    return DocDiff(
        pr_analysis_run_id=pr_run_id,
        artifact_id=row["artifact_id"],
        doc_path=row["doc_path"],
        change_type=row["change_type"],
        unified_diff=row["unified_diff"],
        side_by_side=row["side_by_side"],
    )


def _comment_body(impact: dict[str, Any], diffs: list[dict[str, Any]]) -> str:
    marker = "<!-- aura-pr-review -->"
    severity = impact["severity_counts"]
    lines = [
        marker,
        "## Aura Change Impact Summary",
        "",
        f"- Critical: {severity.get('critical', 0)}",
        f"- Warning: {severity.get('warning', 0)}",
        f"- Info: {severity.get('info', 0)}",
        f"- Documentation diffs: {len(diffs)}",
        "",
        "### Artifact Changes",
        f"- Added: {len(impact['added'])}",
        f"- Modified: {len(impact['modified'])}",
        f"- Removed: {len(impact['removed'])}",
    ]
    return "\n".join(lines)
