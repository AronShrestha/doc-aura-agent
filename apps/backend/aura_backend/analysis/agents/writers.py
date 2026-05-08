"""Project-level documentation writers.

A single generic writer renders one doc per planned doc-type. The writer
gets only the aggregation slices a `DocTypeSpec` declares it needs (built
by `context.project_summary_context`) plus the repo-analyst summary and
visual context, and produces Markdown with mandatory `[verified: ...]`
citations resolving to lines in the supplied aggregation rows.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from typing import Any

from .clients import TextModelClient
from .context import project_summary_context
from .models import PlannedDoc, VisualContext
from .parsing import markdown_from_text
from ..aggregators import ProjectAggregations
from ..doc_types import DocTypeSpec
from ..types import ExtractedArtifact, GeneratedDocDraft, RepoSnapshot
from ..utils import sha256_text


logger = logging.getLogger(__name__)


# Module-level constants — kept stable so prefix caching remains effective
# across many writer calls in one run.
_VERIFIED_CITATION_RULES = (
    "Verified-by-Source citations are mandatory. Every factual claim about an "
    "API surface, behavior, configuration value, return type, or side effect "
    "MUST end with a citation in this exact form: `[verified: <relpath>:L<start>-L<end>]`.\n"
    "Rules:\n"
    "- The relpath and line range MUST come from the supplied aggregations. "
    "Do not cite line ranges you cannot see in the context.\n"
    "- If you have no line range for a claim, write the claim WITHOUT a citation "
    "AND prefix the sentence with `_unverified:_` so the verifier can flag it.\n"
    "- Citations attach to a sentence, not a section. Place them at the end of "
    "the sentence, before the period.\n"
    "- Do not invent behavior. If facts are missing from the context, say so."
)

_MERMAID_GUIDANCE = (
    "Diagrams (Mermaid) — when, and how:\n"
    "- Add ONE Mermaid diagram per document ONLY when it materially clarifies "
    "structure that prose cannot convey crisply. Skip diagrams for pure "
    "tables, glossaries, or single-component subjects.\n"
    "- Strong fits: system architecture (`flowchart LR` of layers), workflows "
    "(`sequenceDiagram` actor → API → service → store), data models (`erDiagram` "
    "with relationships), ML pipelines (`flowchart TD` of stages), state "
    "stores (`flowchart LR` of producers → store → consumers), module map "
    "(`flowchart LR` of package fan-in/fan-out, only when ≤ 12 nodes).\n"
    "- Use a fenced ```mermaid block. Keep it small: ≤ ~14 nodes / ≤ ~20 edges. "
    "Prefer short labels. Group related nodes with `subgraph`.\n"
    "- Apply colour to convey meaning, not decoration. Reuse this palette by "
    "attaching `classDef` and `class` lines:\n"
    "  classDef entry  fill:#eef2ff,stroke:#6366f1,color:#1e1b4b;\n"
    "  classDef svc    fill:#fdf2f8,stroke:#ec4899,color:#831843;\n"
    "  classDef store  fill:#ecfdf5,stroke:#10b981,color:#064e3b;\n"
    "  classDef ext    fill:#fffbeb,stroke:#f59e0b,color:#78350f;\n"
    "  classDef warn   fill:#fef2f2,stroke:#ef4444,color:#7f1d1d;\n"
    "  Map: entry=user/route/CLI input; svc=internal service/handler; "
    "store=DB/cache/queue/state; ext=third-party API/integration; warn=error "
    "path or risky boundary.\n"
    "- Every node label MUST correspond to something in the supplied "
    "aggregations (a module, endpoint, model, integration, store). Do not "
    "invent components. Place the diagram immediately AFTER the relevant "
    "section heading, BEFORE the prose that walks it.\n"
    "- Diagrams are visual aids; the citation rules below still apply to all "
    "factual claims in the surrounding prose."
)


_PROJECT_WRITER_SYSTEM_PROMPT = (
    "You are Aura's Project Doc Writer. Produce one Markdown document of the "
    "requested doc type. Use ONLY the supplied aggregations, repo analysis, "
    "and visual context. Documents may be project-level (no entity_focus) or "
    "per-entity (entity_focus is set — describe ONLY that single entity).\n\n"
    "Output requirements:\n"
    "- Return Markdown only. No YAML front matter (Aura adds it).\n"
    "- Start with an H1 matching the requested title.\n"
    "- Immediately after the H1, when entity_focus is set, add a one-line "
    "`**Canonical Locator:** \\``<key>\\``' line (use the entity_focus key/name).\n"
    "- For docs longer than ~3 sections, add a `## Table of Contents` block "
    "right after the locator line — bullet list with markdown anchors "
    "(`- [Section Title](#section-title)`).\n"
    "- Follow the supplied body_outline as section headings; you may add or "
    "merge sections only when justified by the data.\n"
    "- Cite source files using the `[verified: ...]` format below.\n"
    "- For endpoint docs: include both a sample request and a sample response "
    "as fenced ```json blocks. Mark synthesized examples with `_unverified:_`.\n"
    "- For env-var docs: include at least one concrete value example in a "
    "fenced ``` block, plus a `## Security considerations` subsection (warn "
    "against committing secret_like vars).\n"
    "- Cross-link related docs as RELATIVE markdown links to their `.md` "
    "files (e.g. `[StockResponse](../data-models/stockresponse.md)`). The "
    "frontend intercepts these and routes inside the dashboard. Only link to "
    "docs that exist in the supplied aggregations / sibling generation set.\n"
    "- End with a `## Source Provenance` section listing the cited files.\n"
    "- Then a `## Documentation opportunities` section: 2–4 bullet points on "
    "what is NOT documented yet for this subject (gaps, missing schemas, "
    "untested code paths) — this powers the coverage report.\n\n"
    + _MERMAID_GUIDANCE
    + "\n\n"
    + _VERIFIED_CITATION_RULES
)


_CITATION_RE = re.compile(r"\[verified:\s*([^\]:\s]+):L(\d+)-L(\d+)\]")


async def run_project_doc_writer(
    llm: TextModelClient,
    snapshot: RepoSnapshot,
    planned_doc: PlannedDoc,
    spec: DocTypeSpec,
    aggs: ProjectAggregations,
    repo_analysis: dict[str, Any],
    visual_context: list[VisualContext],
    generated_at: str,
    *,
    human_docs: list[ExtractedArtifact] | None = None,
) -> GeneratedDocDraft:
    logger.info(
        "project doc writer started",
        extra={"repo_id": snapshot.repo_id, "agent": "project_writer", "doc_type": spec.id},
    )
    summary_ctx = project_summary_context(
        snapshot, aggs, spec, human_docs=human_docs,
        entity_focus=planned_doc.entity_focus or None,
    )
    user_payload = {
        "summary_context": summary_ctx,
        "repo_analysis": repo_analysis,
        "visual_context": [asdict(v) for v in visual_context if planned_doc.uses_vlm_context],
        "instructions": {
            "title": planned_doc.title,
            "diataxis_type": planned_doc.diataxis_type,
            "target_path": planned_doc.target_path,
        },
    }
    messages = [
        {"role": "system", "content": _PROJECT_WRITER_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, sort_keys=True, default=str)},
    ]
    raw = await llm.complete(messages, temperature=0.2)
    body = markdown_from_text(raw)
    draft = _draft_from_markdown(snapshot, planned_doc, body, generated_at)
    logger.info(
        "project doc writer succeeded",
        extra={"repo_id": snapshot.repo_id, "agent": "project_writer", "doc_type": spec.id},
    )
    return draft


def make_index_doc(
    snapshot: RepoSnapshot,
    docs: list[GeneratedDocDraft],
    generated_at: str,
) -> GeneratedDocDraft:
    """Render a hierarchical-tree index by grouping docs on their slug path."""
    tree = _build_doc_tree(docs)
    lines: list[str] = ["# Aura Documentation Index", ""]
    _render_tree(tree, lines, depth=0)
    content = "\n".join(lines) + "\n"
    full = (
        _front_matter(
            "index",
            "index",
            "Documentation Index",
            [],
            {},
            generated_at,
            snapshot.repo_sha,
            content,
        )
        + "\n"
        + content
    )
    return GeneratedDocDraft(
        artifact_id="index",
        category="index",
        title="Documentation Index",
        slug_path=".aura/docs/index.md",
        content_md=full,
        content_hash=sha256_text(full),
        source_files=[],
        source_lines={},
    )


def _build_doc_tree(docs: list[GeneratedDocDraft]) -> dict[str, Any]:
    tree: dict[str, Any] = {"_children": {}, "_leaves": []}
    for doc in sorted(docs, key=lambda d: d.slug_path):
        if doc.category == "index":
            continue
        rel = doc.slug_path.removeprefix(".aura/docs/")
        parts = rel.split("/")
        node = tree
        for segment in parts[:-1]:
            child = node["_children"].setdefault(segment, {"_children": {}, "_leaves": []})
            node = child
        node["_leaves"].append(doc)
    return tree


def _render_tree(node: dict[str, Any], out: list[str], depth: int) -> None:
    indent = "  " * depth
    for leaf in node["_leaves"]:
        rel = leaf.slug_path.removeprefix(".aura/docs/")
        out.append(f"{indent}- [{leaf.title}]({rel})")
    for name, child in sorted(node["_children"].items()):
        out.append(f"{indent}- **{name}/**")
        _render_tree(child, out, depth + 1)


def _draft_from_markdown(
    snapshot: RepoSnapshot,
    planned_doc: PlannedDoc,
    body: str,
    generated_at: str,
) -> GeneratedDocDraft:
    if not body.strip():
        raise RuntimeError(f"empty_agent_doc:{planned_doc.doc_id}")
    source_files, source_lines = _derive_provenance(body)
    front = _front_matter(
        planned_doc.doc_id,
        planned_doc.category,
        planned_doc.title,
        source_files,
        source_lines,
        generated_at,
        snapshot.repo_sha,
        body,
    )
    full = f"{front}\n{body.strip()}\n"
    return GeneratedDocDraft(
        artifact_id=planned_doc.doc_id,
        category=planned_doc.category,
        title=planned_doc.title,
        slug_path=planned_doc.target_path,
        content_md=full,
        content_hash=sha256_text(full),
        source_files=source_files,
        source_lines=source_lines,
    )


def _derive_provenance(body: str) -> tuple[list[str], dict[str, list[int | None]]]:
    """Compute source_files / source_lines from `[verified: ...]` markers in body.

    The verifier later validates each citation falls within the per-file
    range we record here, so we use the encompassing min/max as the
    allowed range for the file.
    """
    files: dict[str, list[int]] = {}
    for path, start_str, end_str in _CITATION_RE.findall(body):
        try:
            start, end = int(start_str), int(end_str)
        except ValueError:
            continue
        if path in files:
            files[path][0] = min(files[path][0], start)
            files[path][1] = max(files[path][1], end)
        else:
            files[path] = [start, end]
    source_files = sorted(files.keys())
    source_lines: dict[str, list[int | None]] = {p: list(r) for p, r in files.items()}
    return source_files, source_lines


def _front_matter(
    artifact_id: str,
    category: str,
    name: str,
    source_files: list[str],
    source_lines: dict[str, list[int | None]],
    generated_at: str,
    repo_sha: str,
    body: str,
) -> str:
    data = {
        "artifact_id": artifact_id,
        "category": category,
        "name": name,
        "source_files": source_files,
        "source_lines": source_lines,
        "generated_at": generated_at,
        "repo_sha": repo_sha,
        "content_hash": sha256_text(body),
    }
    lines = ["---"]
    for key, value in data.items():
        lines.append(f"{key}: {json.dumps(value)}")
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Deterministic post-hoc docs (no LLM)
# ---------------------------------------------------------------------------


def make_coverage_doc(
    snapshot: RepoSnapshot,
    aggs: ProjectAggregations,
    docs: list[GeneratedDocDraft],
    generated_at: str,
) -> GeneratedDocDraft:
    """Render a deterministic coverage report comparing aggregation entities
    against generated per-entity docs. No LLM call.
    """
    by_path = {d.slug_path: d for d in docs}

    def _slug(text: str) -> str:
        s = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "")).strip("-").lower()
        return s or "item"

    def _coverage(items: list[Any], path_fn) -> tuple[int, int, list[tuple[str, bool, str]]]:
        rows: list[tuple[str, bool, str]] = []
        for item in items:
            name, expected_path = path_fn(item)
            documented = expected_path in by_path
            rows.append((name, documented, expected_path))
        total = len(rows)
        done = sum(1 for r in rows if r[1])
        return total, done, rows

    sections: list[str] = []
    sections.append("# Documentation Coverage Report\n")
    sections.append(
        "_Auto-generated. Compares the entities discovered in the repo "
        "against the per-entity docs Aura emitted this run._\n"
    )

    groups = [
        ("Data models", aggs.data_model_graph.models,
            lambda m: (m.name, f".aura/docs/data-models/{_slug(m.name)}.md")),
        ("Environment variables", aggs.env_var_inventory,
            lambda v: (v.var, f".aura/docs/env-vars/{_slug(v.var)}.md")),
        ("API endpoints",
            [e for g in aggs.endpoint_catalog for e in g.endpoints],
            lambda e: (f"{e.method} {e.path}", f".aura/docs/api/endpoints/{_slug(f'{e.method.lower()}-{e.path}')}.md")),
        ("Config files", aggs.config_inventory,
            lambda c: (c.path, f".aura/docs/config/{_slug(c.path)}.md")),
    ]

    summary_rows = ["| Subject | Documented | Total | Coverage |", "|---|---:|---:|---:|"]
    detail_blocks: list[str] = []
    for label, items, fn in groups:
        if not items:
            continue
        total, done, rows = _coverage(list(items), fn)
        pct = (done * 100 // total) if total else 0
        summary_rows.append(f"| {label} | {done} | {total} | {pct}% |")
        detail_blocks.append(f"\n## {label} ({done}/{total})\n")
        for name, ok, path in rows:
            mark = "✓" if ok else "✗"
            rel = path.removeprefix(".aura/docs/")
            link = f"[`{name}`]({rel})" if ok else f"`{name}`"
            detail_blocks.append(f"- {mark} {link}")
        detail_blocks.append("")

    sections.append("## Summary\n")
    sections.append("\n".join(summary_rows))
    sections.append("\n".join(detail_blocks))
    sections.append(
        "\n## How coverage is computed\n"
        "An entity counts as documented when a per-entity doc exists at its "
        "expected slug path under `.aura/docs/`. The expected path is derived "
        "from a slug of the entity name (`data-models/<slug>.md`, "
        "`env-vars/<slug>.md`, `api/endpoints/<method>-<path>.md`, "
        "`config/<slug>.md`). Use this report to spot gaps before merging.\n"
    )
    sections.append("\n## Source Provenance\n- Computed deterministically from the run aggregations.\n")

    body = "\n".join(sections).rstrip() + "\n"
    front = _front_matter(
        "coverage-report",
        "report",
        "Documentation Coverage Report",
        [],
        {},
        generated_at,
        snapshot.repo_sha,
        body,
    )
    full = f"{front}\n{body}"
    return GeneratedDocDraft(
        artifact_id="coverage-report",
        category="report",
        title="Documentation Coverage Report",
        slug_path=".aura/docs/reports/coverage.md",
        content_md=full,
        content_hash=sha256_text(full),
        source_files=[],
        source_lines={},
    )
