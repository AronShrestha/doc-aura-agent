from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from .clients import TextModelClient
from .models import DocumentationPlan, VerificationReport
from .parsing import json_from_text
from ..types import GeneratedDocDraft, RepoSnapshot


logger = logging.getLogger(__name__)


async def run_verifier_agent(
    llm: TextModelClient,
    snapshot: RepoSnapshot,
    plan: DocumentationPlan,
    docs: list[GeneratedDocDraft],
    manifest: dict[str, Any],
) -> VerificationReport:
    logger.info("verifier started", extra={"repo_id": snapshot.repo_id, "agent": "verifier"})
    local_issues = _local_issues(plan, docs, manifest)
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
    passed = bool(data.get("passed", False)) and not local_issues
    unsupported_raw = data.get("unsupported_claims", 0)
    if isinstance(unsupported_raw, list):
        unsupported_count = len(unsupported_raw)
        issues.extend(str(c) for c in unsupported_raw)
    else:
        try:
            unsupported_count = int(unsupported_raw or 0)
        except (TypeError, ValueError):
            unsupported_count = 0
    report = VerificationReport(
        passed=passed,
        citation_coverage=float(data.get("citation_coverage", 0.0) or 0.0),
        unsupported_claims=unsupported_count,
        section_completeness=float(data.get("section_completeness", 0.0) or 0.0),
        issues=issues,
    )
    logger.info("verifier complete", extra={"repo_id": snapshot.repo_id, "agent": "verifier"})
    return report


def _local_issues(plan: DocumentationPlan, docs: list[GeneratedDocDraft], manifest: dict[str, Any]) -> list[str]:
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
    for doc in docs:
        if not doc.content_md.startswith("---"):
            issues.append(f"missing_front_matter:{doc.slug_path}")
        if doc.category not in {"index", "project", "architecture", "report"} and not doc.source_files:
            issues.append(f"missing_source_provenance:{doc.slug_path}")
    return issues
