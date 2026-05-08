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
    """Legacy entrypoint kept for back-compat / direct tests.

    Webhooks should call ``services.pr_orchestrator.run_pr_orchestrator``
    instead, which wraps this flow in a LangGraph state graph and runs
    the dashboard + comment agents.
    """
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
        impact, diff_rows = await compare_runs(session_factory, base_run_id, head_run_id)
        comment = build_default_comment(impact, diff_rows)
        logger.info("pr base/head runs compared", extra={"pr_id": pull_request_id, "pr_run_id": pr_run_id})
        await persist_pr_run(
            session_factory,
            pr_run_id=pr_run_id,
            base_run_id=base_run_id,
            head_run_id=head_run_id,
            impact=impact,
            diff_rows=diff_rows,
            comment=comment,
        )
        try:
            await materialize_shadow_pr(session_factory, pr_run_id)
        except Exception as exc:
            logger.warning("shadow pr materialize failed", extra={"pr_run_id": pr_run_id, "error": str(exc)})
        logger.info("pr analysis succeeded", extra={"pr_id": pull_request_id, "pr_run_id": pr_run_id})
    except Exception as exc:
        logger.exception("pr analysis failed", extra={"pr_id": pull_request_id, "pr_run_id": pr_run_id})
        await mark_pr_run_failed(session_factory, pr_run_id, str(exc))


async def compare_runs(
    session_factory: async_sessionmaker,
    base_run_id: int,
    head_run_id: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Pure compare: returns (impact_summary, diff_rows). No DB writes."""
    impact, diff_rows, _comment = await _compare_runs(session_factory, base_run_id, head_run_id)
    return impact, diff_rows


def build_default_comment(impact: dict[str, Any], diff_rows: list[dict[str, Any]]) -> str:
    """Templated fallback comment used by the legacy entrypoint."""
    head_by_id: dict[str, Artifact] = {}
    base_by_id: dict[str, Artifact] = {}
    tiers = impact.get("tiers", {}) or {}
    return _comment_body(impact, diff_rows, head_by_id, base_by_id, tiers)


async def persist_pr_run(
    session_factory: async_sessionmaker,
    *,
    pr_run_id: int,
    base_run_id: int,
    head_run_id: int,
    impact: dict[str, Any],
    diff_rows: list[dict[str, Any]],
    comment: str,
    code_patches: dict[str, str] | None = None,
    mismatch_flags: dict[str, Any] | None = None,
    dashboard_url: str | None = None,
) -> None:
    """Persist orchestrator results onto an existing PrAnalysisRun row."""
    async with session_factory() as session:
        pr_run = (await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.id == pr_run_id))).scalar_one()
        pr_run.status = "succeeded"
        pr_run.base_run_id = base_run_id
        pr_run.head_run_id = head_run_id
        pr_run.impact_summary = impact
        pr_run.review_comment_body = comment
        if code_patches is not None:
            pr_run.code_patches = code_patches
        if mismatch_flags is not None:
            pr_run.mismatch_flags = mismatch_flags
        if dashboard_url is not None:
            pr_run.dashboard_url = dashboard_url
        pr_run.updated_at = datetime.utcnow()
        session.add_all([_doc_diff_row(pr_run_id, row) for row in diff_rows])
        await session.commit()


async def mark_pr_run_failed(session_factory: async_sessionmaker, pr_run_id: int, error: str) -> None:
    async with session_factory() as session:
        pr_run = (await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.id == pr_run_id))).scalar_one()
        pr_run.status = "failed"
        pr_run.error = error
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
    diffs = _doc_diffs(base_docs, head_docs, tiers, direct, base_by_id=base_by_id, head_by_id=head_by_id)
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
    *,
    base_by_id: dict[str, Artifact] | None = None,
    head_by_id: dict[str, Artifact] | None = None,
) -> list[dict[str, Any]]:
    base_doc_by_id = {d.artifact_id: d for d in base_docs}
    head_doc_by_id = {d.artifact_id: d for d in head_docs}
    rows: list[dict[str, Any]] = []
    covered: set[str] = set()
    for aid in sorted(set(base_doc_by_id) | set(head_doc_by_id)):
        before = base_doc_by_id.get(aid)
        after = head_doc_by_id.get(aid)
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
        covered.add(aid)

    # Synthesize per-artifact doc diffs for Direct artifacts that have no
    # GeneratedDoc row (project-level docs only cover aggregates, so a single
    # field/signature change to a model or function would otherwise produce
    # no visible doc diff).
    if base_by_id is not None and head_by_id is not None:
        for aid in sorted(direct):
            if aid in covered:
                continue
            base_art = base_by_id.get(aid)
            head_art = head_by_id.get(aid)
            if not base_art and not head_art:
                continue
            before_text = _render_artifact_card(base_art) if base_art else ""
            after_text = _render_artifact_card(head_art) if head_art else ""
            if before_text == after_text:
                continue
            change_type = "added" if base_art is None else "removed" if head_art is None else "modified"
            ref_art = head_art or base_art
            doc_path = _synthetic_doc_path(ref_art)
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
                    "impact_tier": "Direct",
                    "affected_symbol_ids": [aid],
                    "unified_diff": unified,
                    "side_by_side": _side_by_side(before_text, after_text),
                }
            )
    return rows


def _synthetic_doc_path(art: Artifact) -> str:
    cat = (art.category or "artifact").replace("_", "-")
    name = art.name or art.artifact_id
    return f"{cat}/{name}.md"


def _render_artifact_card(art: Artifact) -> str:
    """Render a small Markdown spec card for one artifact, derived purely
    from its tree-sitter payload. Used as the synthetic 'doc' for Direct
    artifacts that have no LLM-generated doc.
    """
    payload = art.payload or {}
    lines: list[str] = []
    lines.append(f"# {art.name}")
    lines.append("")
    meta = []
    if art.category:
        meta.append(f"**Kind:** `{art.category}`")
    if art.source_file:
        loc = art.source_file
        if art.source_line_start:
            loc = f"{loc}:L{art.source_line_start}"
        meta.append(f"**Source:** `{loc}`")
    if payload.get("language"):
        meta.append(f"**Language:** `{payload['language']}`")
    if meta:
        lines.append(" · ".join(meta))
        lines.append("")
    sig = payload.get("signature")
    if sig:
        lines.append("## Signature")
        lines.append("")
        lang = payload.get("language", "")
        lines.append(f"```{lang}")
        lines.append(str(sig))
        lines.append("```")
        lines.append("")
    fields = payload.get("fields")
    if fields:
        lines.append("## Fields")
        lines.append("")
        lines.append("| Name | Type | Default | Nullable |")
        lines.append("|------|------|---------|----------|")
        for f in fields:
            lines.append(
                f"| `{f.get('name','')}` | `{f.get('type','')}` | "
                f"`{f.get('default') if f.get('default') is not None else ''}` | "
                f"{'yes' if f.get('nullable') else 'no'} |"
            )
        lines.append("")
    base_classes = payload.get("base_classes")
    if base_classes:
        lines.append(f"**Base classes:** {', '.join(f'`{b}`' for b in base_classes)}")
        lines.append("")
    decorators = payload.get("decorators")
    if decorators:
        lines.append(f"**Decorators:** {', '.join(f'`{d}`' for d in decorators)}")
        lines.append("")
    relationships = payload.get("relationships")
    if relationships:
        lines.append("## Relationships")
        lines.append("")
        for r in relationships:
            lines.append(f"- `{r}`")
        lines.append("")
    exports = payload.get("exports")
    if exports:
        lines.append(f"**Exports:** {', '.join(f'`{e}`' for e in exports)}")
        lines.append("")
    imports = payload.get("imports")
    if imports:
        sample = list(imports)[:10]
        lines.append(f"**Imports:** {', '.join(f'`{e}`' for e in sample)}")
        if len(imports) > len(sample):
            lines.append(f"_…and {len(imports) - len(sample)} more_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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
