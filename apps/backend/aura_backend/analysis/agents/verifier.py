from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from typing import Any

from .clients import TextModelClient
from .models import DocumentationPlan, VerificationReport
from .parsing import json_from_text
from ..aggregators import ProjectAggregations
from ..types import GeneratedDocDraft, RepoSnapshot


logger = logging.getLogger(__name__)


# Matches: [verified: relpath/file.py:L12-L34]   or   [verified: file.ts:L7-L7]
_CITATION_RE = re.compile(
    r"\[verified:\s*([^\]:\s]+):L(\d+)-L(\d+)\]"
)


def compute_citation_coverage(
    content_md: str,
    allowed_ranges: dict[str, list[int | None]],
) -> tuple[float, list[str]]:
    """Compute citation coverage and the list of invalid citations.

    Coverage = (paragraphs with ≥1 valid citation) / (paragraphs with claims).
    A "claim paragraph" heuristically excludes empty lines, headings,
    front-matter lines (``key: value``), bullet labels, and code fences.
    A citation is *valid* iff:
      - the cited path appears in ``allowed_ranges``, AND
      - the cited line range is contained within the artifact's range.

    Returns ``(coverage, invalid_citations)``. ``invalid_citations`` is a
    list of human-readable strings describing each rejected marker.
    """
    invalid: list[str] = []
    valid_paragraphs = 0
    claim_paragraphs = 0

    in_code = False
    paragraphs: list[str] = []
    buf: list[str] = []
    for line in content_md.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not line.strip():
            if buf:
                paragraphs.append("\n".join(buf))
                buf = []
            continue
        if line.lstrip().startswith("#"):
            if buf:
                paragraphs.append("\n".join(buf))
                buf = []
            continue
        buf.append(line)
    if buf:
        paragraphs.append("\n".join(buf))

    for para in paragraphs:
        # Strip Aura's front-matter "key: value" lines
        if re.match(r"^[a-z_]+:\s", para) and "\n" not in para.strip():
            continue
        if len(para.strip()) < 20:
            continue  # too short to count as a "claim"
        claim_paragraphs += 1

        markers = _CITATION_RE.findall(para)
        if not markers:
            continue

        para_has_valid = False
        for path, start_str, end_str in markers:
            allowed = allowed_ranges.get(path)
            if allowed is None:
                invalid.append(f"unknown_path:{path}")
                continue
            try:
                start, end = int(start_str), int(end_str)
            except ValueError:
                invalid.append(f"bad_range:{path}:{start_str}-{end_str}")
                continue
            artifact_start = allowed[0] if len(allowed) > 0 else None
            artifact_end = allowed[1] if len(allowed) > 1 else None
            if artifact_start is None or artifact_end is None:
                para_has_valid = True
                continue
            if start < artifact_start or end > artifact_end:
                invalid.append(
                    f"out_of_range:{path}:L{start}-L{end} not in L{artifact_start}-L{artifact_end}"
                )
                continue
            para_has_valid = True

        if para_has_valid:
            valid_paragraphs += 1

    coverage = valid_paragraphs / claim_paragraphs if claim_paragraphs else 1.0
    return coverage, invalid


async def run_verifier_agent(
    llm: TextModelClient,
    snapshot: RepoSnapshot,
    plan: DocumentationPlan,
    docs: list[GeneratedDocDraft],
    manifest: dict[str, Any],
    *,
    aggs: ProjectAggregations | None = None,
) -> VerificationReport:
    logger.info("verifier started", extra={"repo_id": snapshot.repo_id, "agent": "verifier"})
    local_issues = _local_issues(plan, docs, manifest, aggs)
    messages = [
        {
            "role": "system",
            "content": (
                "You are Aura's Verifier Agent. Verify generated living docs. "
                "Return strict JSON with keys: passed, citation_coverage, unsupported_claims, "
                "section_completeness, issues. Reject unsupported claims, missing provenance, malformed front matter, "
                "manifest gaps, or Diataxis mismatch."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "repo_sha": snapshot.repo_sha,
                    "plan": {"rationale": plan.rationale, "docs": [asdict(d) for d in plan.docs]},
                    "docs": [
                        {
                            "artifact_id": d.artifact_id,
                            "category": d.category,
                            "title": d.title,
                            "slug_path": d.slug_path,
                            "source_files": d.source_files[:5],
                            "source_lines": dict(list(d.source_lines.items())[:5]),
                            "content_excerpt": d.content_md[:600],
                        }
                        for d in docs[:30]
                    ],
                    "manifest": manifest,
                    "local_issues": local_issues,
                },
                sort_keys=True,
            ),
        },
    ]
    raw = await llm.complete(messages, temperature=0.0)
    data = json_from_text(raw)
    issues = [str(v) for v in data.get("issues", [])] + local_issues
    hard_local = [i for i in local_issues if not i.startswith("coverage_gap:")]
    passed = bool(data.get("passed", False)) and not hard_local
    unsupported_raw = data.get("unsupported_claims", 0)
    if isinstance(unsupported_raw, list):
        unsupported_count = len(unsupported_raw)
        issues.extend(str(c) for c in unsupported_raw)
    else:
        try:
            unsupported_count = int(unsupported_raw or 0)
        except (TypeError, ValueError):
            unsupported_count = 0

    # Locally compute citation coverage from the rendered markdown — more
    # reliable than asking the LLM to grade itself. Project-level docs all
    # cite source; only the index, glossary, and ADR docs are uncitable.
    UNCITABLE = {"index", "glossary", "adrs"}
    local_coverages: list[float] = []
    invalid_citations: list[str] = []
    for doc in docs:
        if doc.category in UNCITABLE:
            continue
        if not doc.source_lines:
            # Citable category with no source lines = pipeline bug; flag.
            issues.append(f"missing_source_lines:{doc.slug_path}")
            local_coverages.append(0.0)
            continue
        cov, invalid = compute_citation_coverage(doc.content_md, doc.source_lines)
        local_coverages.append(cov)
        if invalid:
            invalid_citations.extend(f"{doc.slug_path}:{msg}" for msg in invalid[:5])
    local_coverage = (
        sum(local_coverages) / len(local_coverages) if local_coverages else 1.0
    )
    if invalid_citations:
        issues.extend(invalid_citations[:20])
    if local_coverages and local_coverage < 0.5:
        issues.append(f"low_citation_coverage:{local_coverage:.2f}")
        passed = False

    llm_coverage = float(data.get("citation_coverage", 0.0) or 0.0)
    final_coverage = max(local_coverage, llm_coverage)

    report = VerificationReport(
        passed=passed,
        citation_coverage=final_coverage,
        unsupported_claims=unsupported_count + len(invalid_citations),
        section_completeness=float(data.get("section_completeness", 0.0) or 0.0),
        issues=issues,
    )
    logger.info(
        "verifier complete",
        extra={
            "repo_id": snapshot.repo_id,
            "agent": "verifier",
            "local_citation_coverage": round(local_coverage, 3),
            "invalid_citations": len(invalid_citations),
        },
    )
    return report


def _local_issues(
    plan: DocumentationPlan,
    docs: list[GeneratedDocDraft],
    manifest: dict[str, Any],
    aggs: ProjectAggregations | None = None,
) -> list[str]:
    issues: list[str] = []
    planned_paths = {doc.target_path for doc in plan.docs}
    doc_paths = {doc.slug_path for doc in docs if doc.category != "index"}
    missing_paths = planned_paths - doc_paths
    if missing_paths:
        issues.append(f"missing_planned_docs:{sorted(missing_paths)}")
    manifest_ids = set((manifest.get("docs") or {}).keys())
    doc_ids = {doc.artifact_id for doc in docs}
    if not doc_ids.issubset(manifest_ids):
        issues.append("manifest_missing_doc_entries")
    uncitable_categories = {"index", "glossary", "adrs"}
    for doc in docs:
        if not doc.content_md.startswith("---"):
            issues.append(f"missing_front_matter:{doc.slug_path}")
        if doc.category not in uncitable_categories and not doc.source_files:
            issues.append(f"missing_source_provenance:{doc.slug_path}")

    if aggs is not None:
        issues.extend(_spec_coverage_issues(plan, docs, aggs))
    return issues


def _spec_coverage_issues(
    plan: DocumentationPlan,
    docs: list[GeneratedDocDraft],
    aggs: ProjectAggregations,
) -> list[str]:
    """Spec-aware soft checks (emitted as `coverage_gap:…`, not blockers).

    The verifier raises only on hard gates above; these annotate the quality
    report so the writer/planner can be tuned.
    """
    issues: list[str] = []
    docs_by_type = {p.doc_type_id: p for p in plan.docs}
    body_by_path = {d.slug_path: d.content_md for d in docs}

    def _body_for(doc_type_id: str) -> str | None:
        planned = docs_by_type.get(doc_type_id)
        if not planned:
            return None
        return body_by_path.get(planned.target_path)

    body = _body_for("api-endpoints")
    if body:
        for group in aggs.endpoint_catalog:
            for ep in group.endpoints:
                if ep.path and ep.path not in body:
                    issues.append(f"coverage_gap:api-endpoints:{ep.method} {ep.path}")

    body = _body_for("config")
    if body:
        for env in aggs.env_var_inventory:
            if env.var not in body:
                issues.append(f"coverage_gap:config:{env.var}")

    body = _body_for("architecture-modules")
    if body:
        for mod in aggs.module_responsibility_map:
            if mod.package_path and mod.package_path not in body:
                issues.append(f"coverage_gap:architecture-modules:{mod.package_path}")

    body = _body_for("api-models")
    if body:
        for model in aggs.data_model_graph.models:
            short = model.name.split(".")[-1]
            if short and short not in body:
                issues.append(f"coverage_gap:api-models:{short}")

    body = _body_for("external-integrations")
    if body:
        for integ in aggs.external_integrations:
            if integ.name not in body:
                issues.append(f"coverage_gap:external-integrations:{integ.name}")

    body = _body_for("frontend-pages")
    if body and aggs.frontend_view.pages:
        for page in aggs.frontend_view.pages:
            if page.path not in body:
                issues.append(f"coverage_gap:frontend-pages:{page.path}")

    return issues
