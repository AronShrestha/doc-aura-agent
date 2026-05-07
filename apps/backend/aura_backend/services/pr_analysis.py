from __future__ import annotations

import difflib
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..analysis.agents.clients import OpenAIChatClient
from ..analysis.agents.pr_reviewer import run_pr_reviewer_agent
from ..config import settings
from ..models import AnalysisRun, Artifact, ArtifactEdge, DocDiff, GeneratedDoc, PrAnalysisRun, PullRequest
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
        base_edges = (await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == base_run_id))).scalars().all()
        head_edges = (await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == head_run_id))).scalars().all()
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
    all_by_id = {**base_by_id, **head_by_id}
    edges = _merged_edges(base_edges, head_edges)
    impacted_neighbors = _related_artifacts(impacted, all_by_id, edges, max_depth=2)
    affected_flows = _affected_flows(impacted, impacted_neighbors, all_by_id, edges)
    impact = {
        "added": [_artifact_summary(head_by_id[aid]) for aid in added],
        "removed": [_artifact_summary(base_by_id[aid]) for aid in removed],
        "modified": [_artifact_summary(head_by_id[aid]) for aid in modified],
        "impacted_neighbors": [_artifact_summary(all_by_id[aid]) for aid in impacted_neighbors],
        "affected_flows": [_artifact_summary(all_by_id[aid]) for aid in affected_flows],
        "unchanged_count": len(unchanged),
        "severity_counts": {level: severities.count(level) for level in ["critical", "warning", "info"]},
    }
    diffs = _doc_diffs(base_docs, head_docs)
    impact["documentation_changes"] = {
        "count": len(diffs),
        "added": sum(1 for diff in diffs if diff["change_type"] == "added"),
        "modified": sum(1 for diff in diffs if diff["change_type"] == "modified"),
        "removed": sum(1 for diff in diffs if diff["change_type"] == "removed"),
        "paths": [diff["doc_path"] for diff in diffs[:20]],
    }
    logger.info("pr impact comparison complete", extra={"event": "pr_compare_complete"})
    return impact, diffs, await _review_comment_body(impact, diffs)


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


def _merged_edges(base_edges: list[ArtifactEdge], head_edges: list[ArtifactEdge]) -> list[ArtifactEdge]:
    merged: dict[tuple[str, str, str], ArtifactEdge] = {}
    for edge in [*base_edges, *head_edges]:
        merged[(edge.src_artifact_id, edge.dst_artifact_id, edge.kind)] = edge
    return list(merged.values())


def _related_artifacts(
    impacted_artifact_ids: list[str],
    artifacts_by_id: dict[str, Artifact],
    edges: list[ArtifactEdge],
    *,
    max_depth: int,
) -> list[str]:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge.src_artifact_id, set()).add(edge.dst_artifact_id)
        adjacency.setdefault(edge.dst_artifact_id, set()).add(edge.src_artifact_id)

    seen = set(impacted_artifact_ids)
    frontier = set(impacted_artifact_ids)
    neighbors: set[str] = set()
    for _ in range(max_depth):
        next_frontier: set[str] = set()
        for node in frontier:
            for neighbor in adjacency.get(node, set()):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                next_frontier.add(neighbor)
                if neighbor in artifacts_by_id:
                    neighbors.add(neighbor)
        frontier = next_frontier
        if not frontier:
            break

    ordered = sorted(
        neighbors,
        key=lambda artifact_id: (
            artifacts_by_id[artifact_id].category,
            artifacts_by_id[artifact_id].name,
        ),
    )
    return ordered[:25]


def _affected_flows(
    impacted_artifact_ids: list[str],
    impacted_neighbors: list[str],
    artifacts_by_id: dict[str, Artifact],
    edges: list[ArtifactEdge],
) -> list[str]:
    candidate_ids = set(impacted_artifact_ids) | set(impacted_neighbors)
    flow_ids = {
        artifact_id
        for artifact_id, artifact in artifacts_by_id.items()
        if artifact.category == "flow" and artifact_id in candidate_ids
    }

    for edge in edges:
        if edge.kind != "part_of_flow":
            continue
        if edge.src_artifact_id in candidate_ids and artifacts_by_id.get(edge.dst_artifact_id, None) and artifacts_by_id[edge.dst_artifact_id].category == "flow":
            flow_ids.add(edge.dst_artifact_id)
        if edge.dst_artifact_id in candidate_ids and artifacts_by_id.get(edge.src_artifact_id, None) and artifacts_by_id[edge.src_artifact_id].category == "flow":
            flow_ids.add(edge.src_artifact_id)

    return sorted(flow_ids, key=lambda artifact_id: artifacts_by_id[artifact_id].name)


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
    severity = impact["severity_counts"]
    flow_names = [flow["name"] for flow in impact.get("affected_flows", [])[:6]]
    changed_artifacts = [*impact.get("added", []), *impact.get("modified", []), *impact.get("removed", [])]
    impacted_neighbors = [artifact["name"] for artifact in impact.get("impacted_neighbors", [])[:6]]
    docs = impact.get("documentation_changes") or {}
    lines = [
        "<!-- aura-pr-review -->",
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
    if changed_artifacts:
        lines.extend(
            [
                "",
                "### Key Changes",
                *[
                    f"- {artifact['name']} ({artifact['category']})"
                    for artifact in changed_artifacts[:8]
                ],
            ]
        )
    if impacted_neighbors:
        lines.extend(["", "### Nearby Impact", *[f"- {name}" for name in impacted_neighbors]])
    if flow_names:
        lines.extend(["", "### Affected Flows", *[f"- {name}" for name in flow_names]])
    if docs:
        lines.extend(
            [
                "",
                "### Documentation Follow-up",
                f"- Docs added: {docs.get('added', 0)}",
                f"- Docs modified: {docs.get('modified', 0)}",
                f"- Docs removed: {docs.get('removed', 0)}",
                "- Approve the PR or confirm docs follow-up to open the companion docs PR.",
            ]
        )
    return "\n".join(lines)


async def _review_comment_body(impact: dict[str, Any], diffs: list[dict[str, Any]]) -> str:
    try:
        body = await run_pr_reviewer_agent(
            OpenAIChatClient(
                settings.llm_base_url,
                settings.llm_model,
                settings.llm_api_key,
                settings.llm_timeout_seconds,
                settings.llm_max_tokens,
            ),
            impact,
            diffs,
        )
        if "<!-- aura-pr-review -->" not in body:
            body = "<!-- aura-pr-review -->\n" + body.lstrip()
        return body
    except Exception:
        logger.exception("pr reviewer agent failed; falling back to deterministic comment")
        return _comment_body(impact, diffs)
