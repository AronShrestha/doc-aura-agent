from __future__ import annotations

import difflib
import logging
from datetime import datetime
from typing import Any

from collections import defaultdict, deque

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..models import AnalysisRun, Artifact, ArtifactEdge, DocDiff, GeneratedDoc, PrAnalysisRun, PullRequest
from ..analysis.pipeline import run_static_analysis_for_ref
from .shadow_pr import materialize_shadow_pr


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
        try:
            await materialize_shadow_pr(session_factory, pr_run_id)
        except Exception as exc:
            logger.warning("shadow pr materialize failed", extra={"pr_run_id": pr_run_id, "error": str(exc)})
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
        head_edges = (await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == head_run_id))).scalars().all()
        base_edges = (await session.execute(select(ArtifactEdge).where(ArtifactEdge.run_id == base_run_id))).scalars().all()

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

    # Direct = artifact whose hash changed or that was added/removed
    direct = set(added) | set(removed) | set(modified)

    # Build reverse-edge index over the union of base + head edges so
    # callers of *removed* artifacts (whose edges only exist in base)
    # still get their tier upgraded.
    reverse_edges: dict[str, list[str]] = defaultdict(list)
    seen_pairs: set[tuple[str, str]] = set()
    for edge in list(head_edges) + list(base_edges):
        if edge.kind not in ("calls", "imports", "uses_model", "extends", "implements"):
            continue
        key = (edge.src_artifact_id, edge.dst_artifact_id)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        reverse_edges[edge.dst_artifact_id].append(edge.src_artifact_id)

    tiers = _compute_impact_tiers(direct, reverse_edges)

    impact = {
        "added": [_artifact_summary(head_by_id[aid]) for aid in added],
        "removed": [_artifact_summary(base_by_id[aid]) for aid in removed],
        "modified": [_artifact_summary(head_by_id[aid]) for aid in modified],
        "unchanged_count": len(unchanged),
        "tier_counts": _tier_counts(tiers),
        "tiers": tiers,
        "severity_counts": {  # legacy field, keep for back-compat
            level: sum(1 for aid in direct if _severity((head_by_id.get(aid) or base_by_id.get(aid)), aid in removed) == level)
            for level in ("critical", "warning", "info")
        },
    }
    diffs = _doc_diffs(base_docs, head_docs, tiers, direct)
    logger.info("pr impact comparison complete", extra={"event": "pr_compare_complete"})
    return impact, diffs, _comment_body(impact, diffs, head_by_id, base_by_id, tiers)


def _compute_impact_tiers(
    direct: set[str],
    reverse_edges: dict[str, list[str]],
    *,
    medium_cap: int = 20,
) -> dict[str, str]:
    """BFS over reverse edges from each Direct artifact.

    Tier semantics:
    - Direct: artifact's semantic hash changed, or artifact added/removed
    - High:   1-hop predecessor of any Direct artifact
    - Medium: 2-hop predecessor; capped at ``medium_cap`` by edge fan-in.
    """
    tiers: dict[str, str] = {aid: "Direct" for aid in direct}

    # 1-hop
    high: set[str] = set()
    for aid in direct:
        for src in reverse_edges.get(aid, []):
            if src not in tiers:
                high.add(src)
    for aid in high:
        tiers[aid] = "High"

    # 2-hop
    medium_candidates: dict[str, int] = defaultdict(int)
    for aid in high:
        for src in reverse_edges.get(aid, []):
            if src not in tiers:
                medium_candidates[src] += 1
    # cap by edge count, descending
    capped = sorted(medium_candidates.items(), key=lambda kv: -kv[1])[:medium_cap]
    for aid, _ in capped:
        tiers[aid] = "Medium"

    return tiers


def _tier_counts(tiers: dict[str, str]) -> dict[str, int]:
    out = {"Direct": 0, "High": 0, "Medium": 0}
    for tier in tiers.values():
        if tier in out:
            out[tier] += 1
    return out


def _artifact_fingerprint(artifact: Artifact) -> str:
    """Stable fingerprint used to detect 'modified' artifacts across PR runs.

    Prefers the tree-sitter ``semantic_hash`` (from
    ``analysis.ingestion_bridge``) which is invariant under cosmetic
    edits — renamed locals, reformatting, added comments. Falls back to
    a payload-stringified fingerprint for artifacts that did not match
    a tree-sitter symbol (modules, endpoints, config, env vars).
    """
    payload = dict(artifact.payload or {})
    semantic = payload.get("semantic_hash")
    if semantic:
        return f"sh:{artifact.category}:{artifact.source_file}:{semantic}"
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


def _doc_diffs(
    base_docs: list[GeneratedDoc],
    head_docs: list[GeneratedDoc],
    tiers: dict[str, str],
    direct: set[str],
) -> list[dict[str, Any]]:
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
        tier = tiers.get(aid, "Direct" if aid in direct else "Medium")
        rows.append(
            {
                "artifact_id": aid,
                "doc_path": doc_path,
                "change_type": change_type,
                "impact_tier": tier,
                "affected_symbol_ids": [aid],
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
        impact_tier=row.get("impact_tier", "Medium"),
        affected_symbol_ids=row.get("affected_symbol_ids", []),
        unified_diff=row["unified_diff"],
        side_by_side=row["side_by_side"],
    )


def _comment_body(
    impact: dict[str, Any],
    diffs: list[dict[str, Any]],
    head_by_id: dict[str, Artifact],
    base_by_id: dict[str, Artifact],
    tiers: dict[str, str],
) -> str:
    marker = "<!-- aura-pr-review -->"
    counts = impact["tier_counts"]
    direct_artifacts = [aid for aid, t in tiers.items() if t == "Direct"]
    top_direct = direct_artifacts[:3]
    direct_lines = []
    for aid in top_direct:
        art = head_by_id.get(aid) or base_by_id.get(aid)
        if art:
            loc = f"{art.source_file}:L{art.source_line_start}" if art.source_file else art.name
            direct_lines.append(f"  - `{art.name}` ({art.category}) — {loc}")
    lines = [
        marker,
        "## 📚 Aura Change Impact",
        "",
        f"**{counts.get('Direct', 0)} Direct · {counts.get('High', 0)} High · {counts.get('Medium', 0)} Medium**",
        f"📝 {len(diffs)} doc diffs generated",
        "",
        "### Direct changes",
    ]
    if direct_lines:
        lines.extend(direct_lines)
    else:
        lines.append("  _(none)_")
    lines += [
        "",
        "### Artifact changes",
        f"- Added: {len(impact['added'])}",
        f"- Modified: {len(impact['modified'])}",
        f"- Removed: {len(impact['removed'])}",
    ]
    return "\n".join(lines)
