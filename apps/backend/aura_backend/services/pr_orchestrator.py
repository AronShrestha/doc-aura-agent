"""PR Orchestrator — LangGraph state graph driving two child agents.

Flow:

    upsert_pr_run
        ├─► analyze_base ─┐
        └─► analyze_head ─┤
                          ▼
                       compare
                          │
                          ▼
                    dashboard_agent          (code patches + mismatch detection)
                          │
                          ▼
                       persist
                          │
                          ▼
                    comment_agent            (always summary; mismatch block when flagged)
                          │
                          ▼
                    post_comment             (POST/PATCH GitHub issue comment)

Each node only mutates its slice of ``PrOrchestratorState`` so failures
in one branch don't leave the DB in an inconsistent state.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from functools import partial
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..analysis.agents.dashboard import run_dashboard_agent
from ..analysis.agents.doc_updater import update_doc_for_change
from ..analysis.agents.pr_reviewer import (
    assemble_comment,
    build_mismatch_comment,
    build_summary_comment,
    maybe_rewrite_with_llm,
)
from ..analysis.pipeline import _pipeline_llm_client, run_static_analysis_for_ref
from ..config import settings
from ..models import AnalysisRun, Artifact, DocDiff, GeneratedDoc, GithubOAuthToken, PrAnalysisRun, PullRequest, Repo
from .github_app import GithubAppError, build_app_jwt, create_installation_token
from .pr_analysis import compare_runs, mark_pr_run_failed, persist_pr_run
from .shadow_pr import materialize_shadow_pr


logger = logging.getLogger(__name__)


class PrOrchestratorState(TypedDict, total=False):
    pull_request_id: int
    pr_run_id: int
    base_run_id: int
    head_run_id: int
    impact: dict[str, Any]
    doc_diffs: list[dict[str, Any]]
    code_patches: dict[str, str]
    mismatch_flags: dict[str, Any]
    summary_comment: str
    mismatch_comment: str
    final_comment: str
    dashboard_url: str
    error: str


# ──────────────────────────────────────────────────────────────────────
# Nodes
# ──────────────────────────────────────────────────────────────────────


async def _node_create_run(session_factory, state: PrOrchestratorState) -> PrOrchestratorState:
    pull_request_id = state["pull_request_id"]
    async with session_factory() as session:
        pr_run = PrAnalysisRun(pull_request_id=pull_request_id, status="running")
        session.add(pr_run)
        await session.commit()
        return {"pr_run_id": pr_run.id}


async def _node_analyze(session_factory, pull_request_id: int) -> tuple[int, int]:
    async with session_factory() as session:
        pr = (await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))).scalar_one()
        repo_id, base_ref, base_sha, head_ref, head_sha = pr.repo_id, pr.base_ref, pr.base_sha, pr.head_ref, pr.head_sha
    base_run_id = await run_static_analysis_for_ref(session_factory, repo_id, base_ref, base_sha, is_pr_run=True)
    head_run_id = await run_static_analysis_for_ref(session_factory, repo_id, head_ref, head_sha, is_pr_run=True)
    return base_run_id, head_run_id


async def _node_compare(session_factory, state: PrOrchestratorState) -> PrOrchestratorState:
    base_run_id, head_run_id = await _node_analyze(session_factory, state["pull_request_id"])
    impact, doc_diffs = await compare_runs(session_factory, base_run_id, head_run_id)
    return {"base_run_id": base_run_id, "head_run_id": head_run_id, "impact": impact, "doc_diffs": doc_diffs}


async def _node_dashboard(session_factory, state: PrOrchestratorState) -> PrOrchestratorState:
    out = await run_dashboard_agent(
        session_factory,
        state["pull_request_id"],
        state["impact"],
        state["doc_diffs"],
        state["head_run_id"],
    )
    return {"code_patches": out["code_patches"], "mismatch_flags": out["mismatch_flags"]}


async def _node_doc_update(session_factory, state: PrOrchestratorState) -> PrOrchestratorState:
    """Use LLM to minimally update each canonical doc whose source files
    are touched by Direct artifacts. Adds resulting before/after rows to
    ``doc_diffs`` (in addition to existing synthetic per-artifact cards).
    Updated docs are NOT persisted to canonical GeneratedDoc here — that
    happens on PR merge."""
    impact = state.get("impact") or {}
    code_patches = state.get("code_patches") or {}
    direct = [a for a in (impact.get("modified") or []) + (impact.get("added") or []) + (impact.get("removed") or [])]
    direct_files = {a.get("source_file") for a in direct if a.get("source_file")}
    logger.info(
        "doc updater entry",
        extra={
            "event": "doc_update_entry",
            "pr_id": state.get("pull_request_id"),
            "direct": len(direct),
            "direct_files": len(direct_files),
            "code_patch_files": len(code_patches),
        },
    )
    if not direct or not direct_files:
        logger.info(
            "doc updater early-return: no direct artifacts with source files",
            extra={"event": "doc_update_skip", "pr_id": state.get("pull_request_id"), "reason": "no_direct"},
        )
        return {}

    async with session_factory() as session:
        pr = (await session.execute(select(PullRequest).where(PullRequest.id == state["pull_request_id"]))).scalar_one()
        repo = (await session.execute(select(Repo).where(Repo.id == pr.repo_id))).scalar_one()
        canonical = (
            await session.execute(
                select(AnalysisRun)
                .where(
                    AnalysisRun.repo_id == pr.repo_id,
                    AnalysisRun.is_pr_run.is_(False),
                    AnalysisRun.status == "succeeded",
                    AnalysisRun.branch == repo.default_branch,
                )
                .order_by(AnalysisRun.id.desc())
            )
        ).scalars().first()
        if not canonical:
            logger.info("no canonical run; skipping doc updater", extra={"pr_id": state["pull_request_id"]})
            return {}
        canonical_docs = (
            await session.execute(select(GeneratedDoc).where(GeneratedDoc.run_id == canonical.id))
        ).scalars().all()

    if not canonical_docs:
        logger.info(
            "doc updater early-return: canonical has no GeneratedDoc rows",
            extra={"event": "doc_update_skip", "pr_id": state["pull_request_id"], "canonical_run_id": canonical.id, "reason": "canonical_no_docs"},
        )
        return {}

    # Build inverted indexes once over the canonical docs (O(N_docs × tokens)
    # at index time; O(1) per Direct artifact lookup at match time).
    file_to_docs, token_to_docs = _build_doc_indexes(canonical_docs)

    # Walk Direct artifacts and accumulate STRICTLY-affected docs.
    # Match rule (must satisfy BOTH):
    #   1. Doc's source_files include the Direct artifact's source_file
    #      (exact path or basename) — i.e. the doc is *about* code that
    #      actually changed in the PR.
    #   2. The Direct artifact's qualified_name OR bare name appears as a
    #      token in the doc's content — i.e. the doc actually mentions
    #      the changed symbol.
    # The strict AND eliminates noise from project-level docs that merely
    # cross-reference common types (Repo, Session, User) without owning
    # them, and from doc files that share a category but not a symbol.
    affected_map: dict[int, dict[str, Any]] = {}  # doc.id → entry
    for art in direct:
        sf = art.get("source_file")
        if not sf:
            continue
        file_hits: set = set()
        for d in file_to_docs.get(sf, ()):
            file_hits.add(d)
        base = sf.rsplit("/", 1)[-1]
        if base != sf:
            for d in file_to_docs.get(base, ()):
                file_hits.add(d)
        if not file_hits:
            continue
        token_hits: set = set()
        for tok in _direct_tokens(art):
            for d in token_to_docs.get(tok, ()):
                token_hits.add(d)
        confirmed = file_hits & token_hits if token_hits else file_hits
        # If the artifact has NO meaningful tokens (e.g. category=module),
        # fall back to file_hits — module docs are about the file itself.
        if not confirmed:
            continue
        for doc in confirmed:
            entry = affected_map.setdefault(
                doc.id,
                {"doc": doc, "arts": [], "art_ids": set(), "files": set()},
            )
            aid = art.get("artifact_id")
            if aid and aid not in entry["art_ids"]:
                entry["art_ids"].add(aid)
                entry["arts"].append(art)
            entry["files"].add(sf)

    affected: list[tuple[GeneratedDoc, list[dict[str, Any]], dict[str, str]]] = []
    for entry in affected_map.values():
        doc_patches = {f: code_patches[f] for f in entry["files"] if f in code_patches}
        if not doc_patches:
            continue
        affected.append((entry["doc"], entry["arts"], doc_patches))

    if not affected:
        logger.info("no canonical docs intersect direct files", extra={"pr_id": state["pull_request_id"]})
        return {}

    llm = _pipeline_llm_client()
    concurrency = max(1, int(getattr(settings, "llm_max_concurrency", 4)))
    sem = asyncio.Semaphore(concurrency)
    logger.info(
        "doc updater LLM run starting",
        extra={
            "event": "doc_update_llm_start",
            "pr_id": state["pull_request_id"],
            "affected_docs": len(affected),
            "concurrency": concurrency,
        },
    )

    async def _one(doc, doc_arts, doc_patches):
        async with sem:
            logger.info(
                "doc updater LLM call",
                extra={
                    "event": "doc_update_llm_call",
                    "pr_id": state["pull_request_id"],
                    "slug": doc.slug_path,
                    "patch_files": list(doc_patches.keys()),
                },
            )
            # Strip frontmatter before sending to LLM and before diffing —
            # so artifact_id / generated_at / content_hash never appear in
            # the rendered PR diff. Also stops the LLM from echoing them.
            base_clean = _strip_frontmatter(doc.content_md or "")
            try:
                updated = await update_doc_for_change(llm, base_clean, doc_patches, doc_arts)
            except Exception as exc:
                logger.warning("doc updater failed for doc", extra={"slug": doc.slug_path, "error": str(exc)})
                return None
            updated = _strip_frontmatter(updated or "")
        return (doc, doc_arts, base_clean, updated)

    results = await asyncio.gather(*[_one(d, a, p) for d, a, p in affected])
    extra_rows: list[dict[str, Any]] = []
    for r in results:
        if r is None:
            continue
        doc, doc_arts, base_clean, updated = r
        if updated.strip() == base_clean.strip():
            logger.info(
                "doc updater llm returned identical doc",
                extra={"event": "doc_update_unchanged", "pr_id": state["pull_request_id"], "slug": doc.slug_path},
            )
            continue
        if not _diff_mentions_direct_symbol(base_clean, updated, doc_arts):
            logger.info(
                "doc updater dropped: no direct symbol in diff",
                extra={
                    "event": "doc_update_drop_irrelevant",
                    "pr_id": state["pull_request_id"],
                    "slug": doc.slug_path,
                },
            )
            continue
        extra_rows.append(_build_doc_diff_row(doc, base_clean, updated))

    merged = (state.get("doc_diffs") or []) + extra_rows
    logger.info(
        "doc updater produced rows",
        extra={"pr_id": state["pull_request_id"], "count": len(extra_rows), "affected_docs": len(affected)},
    )
    return {"doc_diffs": merged}


# Strip leading YAML frontmatter (--- ... ---) and any leading naked
# key: value metadata block before computing diffs / sending to LLM.
_FRONTMATTER_FENCE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_NAKED_META_LINE = re.compile(
    r"^(artifact_id|category|name|source_files|source_lines|generated_at|repo_sha|content_hash)\s*:",
    re.MULTILINE,
)


def _strip_frontmatter(md: str) -> str:
    if not md:
        return md
    out = _FRONTMATTER_FENCE.sub("", md, count=1).lstrip("\n")
    # Strip a leading run of naked key: value metadata lines (no fence).
    lines = out.splitlines(keepends=True)
    keep_from = 0
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if not stripped:
            keep_from = i + 1
            continue
        if _NAKED_META_LINE.match(stripped):
            keep_from = i + 1
            continue
        break
    return "".join(lines[keep_from:])


# Identifier-like tokens (Python/JS/TS symbol shapes). Excludes pure-numeric.
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\.]{2,}")
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "this", "that", "from", "into", "any",
        "all", "not", "but", "use", "uses", "used", "using", "are", "was",
        "were", "have", "has", "had", "will", "can", "may", "should", "must",
        "may", "true", "false", "none", "null", "self", "cls", "args", "kwargs",
        "data", "type", "kind", "name", "value", "field", "fields", "list",
        "dict", "str", "int", "bool", "float", "object", "class", "function",
        "module", "method", "param", "params", "return", "returns", "yields",
        "note", "see", "also", "example", "examples", "input", "output",
        "result", "results", "default", "optional", "required",
    }
)


def _tokenize_doc(content: str) -> set[str]:
    """Extract identifier-shape tokens from doc content. Filters stopwords
    and very short tokens. Includes both qualified ('a.b.c') and bare
    ('c') forms so lookup matches either."""
    if not content:
        return set()
    out: set[str] = set()
    for m in _IDENT_RE.findall(content):
        if not m:
            continue
        out.add(m)
        if "." in m:
            tail = m.rsplit(".", 1)[-1]
            if len(tail) >= 4 and tail.lower() not in _STOPWORDS:
                out.add(tail)
    return {t for t in out if t.lower() not in _STOPWORDS and len(t) >= 4}


def _direct_tokens(art: dict[str, Any]) -> list[str]:
    """Lookup tokens for one Direct artifact. Prefer qualified_name (unique)
    plus the bare last segment if it isn't a common word."""
    tokens: list[str] = []
    for key in ("qualified_name", "name"):
        n = art.get(key)
        if not n:
            continue
        tokens.append(n)
        tail = n.rsplit(".", 1)[-1]
        if tail and len(tail) >= 4 and tail.lower() not in _STOPWORDS:
            tokens.append(tail)
    return list(dict.fromkeys(tokens))  # dedupe, preserve order


def _build_doc_indexes(docs):
    """Single-pass build of two reverse indexes:
       - file_to_docs: source_file (or basename) -> list[GeneratedDoc]
       - token_to_docs: identifier-token -> list[GeneratedDoc]
    Each doc is added at most once per key. O(N_docs × |content|) total.
    """
    file_to_docs: dict[str, list] = {}
    token_to_docs: dict[str, list] = {}
    for doc in docs:
        for f in doc.source_files or []:
            file_to_docs.setdefault(f, []).append(doc)
            base = f.rsplit("/", 1)[-1]
            if base != f:
                file_to_docs.setdefault(base, []).append(doc)
        for tok in _tokenize_doc(doc.content_md or ""):
            token_to_docs.setdefault(tok, []).append(doc)
    return file_to_docs, token_to_docs


def _diff_mentions_direct_symbol(
    before_md: str,
    after_md: str,
    doc_arts: list[dict[str, Any]],
) -> bool:
    """True if the LLM's edit set mentions any Direct artifact's name/qualified_name.
    Filters out whitespace-only or unrelated rephrasings."""
    import difflib

    tokens: set[str] = set()
    for art in doc_arts:
        for key in ("name", "qualified_name"):
            n = art.get(key)
            if not n:
                continue
            tokens.add(n)
            short = n.rsplit(".", 1)[-1]
            if short and len(short) >= 3:
                tokens.add(short)
    if not tokens:
        return True  # be permissive if we have no symbol info
    diff_iter = difflib.unified_diff(before_md.splitlines(), after_md.splitlines(), lineterm="")
    changed: list[str] = []
    for ln in diff_iter:
        if ln.startswith("+++") or ln.startswith("---") or ln.startswith("@@"):
            continue
        if ln.startswith("+") or ln.startswith("-"):
            changed.append(ln[1:])
    for line in changed:
        for tok in tokens:
            if tok and tok in line:
                return True
    return False


def _build_doc_diff_row(doc: GeneratedDoc, before_text: str, after_text: str) -> dict[str, Any]:
    import difflib

    unified = "\n".join(
        difflib.unified_diff(
            before_text.splitlines(),
            after_text.splitlines(),
            fromfile=f"base/{doc.slug_path}",
            tofile=f"head/{doc.slug_path}",
            lineterm="",
        )
    )
    matcher = difflib.SequenceMatcher(a=before_text.splitlines(), b=after_text.splitlines())
    side_rows = []
    base_lines = before_text.splitlines()
    head_lines = after_text.splitlines()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        side_rows.append({"type": tag, "base": base_lines[i1:i2], "head": head_lines[j1:j2]})
    return {
        "artifact_id": doc.artifact_id,
        "doc_path": doc.slug_path,
        "change_type": "modified",
        "impact_tier": "Direct",
        "affected_symbol_ids": [doc.artifact_id],
        "unified_diff": unified,
        "side_by_side": {"rows": side_rows},
    }


async def _node_persist(session_factory, state: PrOrchestratorState) -> PrOrchestratorState:
    await persist_pr_run(
        session_factory,
        pr_run_id=state["pr_run_id"],
        base_run_id=state["base_run_id"],
        head_run_id=state["head_run_id"],
        impact=state["impact"],
        diff_rows=state["doc_diffs"],
        comment="",  # filled by comment node
        code_patches=state.get("code_patches"),
        mismatch_flags=state.get("mismatch_flags"),
        dashboard_url=state.get("dashboard_url"),
    )
    try:
        await materialize_shadow_pr(session_factory, state["pr_run_id"])
    except Exception as exc:
        logger.warning("shadow pr materialize failed", extra={"pr_run_id": state["pr_run_id"], "error": str(exc)})
    return {}


async def _node_comment(session_factory, state: PrOrchestratorState) -> PrOrchestratorState:
    dashboard_url = state.get("dashboard_url", "")
    summary = build_summary_comment(state["impact"], state["doc_diffs"], dashboard_url)
    mismatch = build_mismatch_comment(state.get("mismatch_flags") or {}, state["doc_diffs"], dashboard_url)
    body = assemble_comment(summary, mismatch)

    if settings.pr_reviewer_llm_enabled:
        try:
            llm = _pipeline_llm_client()
            body = await maybe_rewrite_with_llm(
                llm,
                body,
                impact=state["impact"],
                mismatch_flags=state.get("mismatch_flags") or {},
            )
        except Exception as exc:
            logger.warning("pr_reviewer llm disabled by failure", extra={"error": str(exc)})

    async with session_factory() as session:
        pr_run = (await session.execute(select(PrAnalysisRun).where(PrAnalysisRun.id == state["pr_run_id"]))).scalar_one()
        pr_run.review_comment_body = body
        pr_run.updated_at = datetime.utcnow()
        await session.commit()

    return {"summary_comment": summary, "mismatch_comment": mismatch, "final_comment": body}


async def _node_post(session_factory, state: PrOrchestratorState) -> PrOrchestratorState:
    body = state.get("final_comment") or ""
    if not body:
        return {}
    pull_request_id = state["pull_request_id"]
    async with session_factory() as session:
        pr = (await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))).scalar_one()
        repo = (await session.execute(select(Repo).where(Repo.id == pr.repo_id))).scalar_one()
        token = await _resolve_token(session, repo)
        if not token:
            logger.warning("skipping pr comment; no github token", extra={"pr_id": pull_request_id})
            return {}
        comment_id = pr.comment_id
        owner, name, number = repo.owner, repo.name, pr.number

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        if comment_id:
            resp = await client.patch(
                f"https://api.github.com/repos/{owner}/{name}/issues/comments/{comment_id}",
                headers=headers,
                json={"body": body},
            )
            if resp.status_code < 400:
                logger.info("pr comment updated", extra={"pr_id": pull_request_id})
                return {}
            logger.warning("pr comment patch failed; falling back to POST", extra={"pr_id": pull_request_id, "status": resp.status_code})
        resp = await client.post(
            f"https://api.github.com/repos/{owner}/{name}/issues/{number}/comments",
            headers=headers,
            json={"body": body},
        )
    if resp.status_code < 400:
        new_id = str(resp.json().get("id", ""))
        async with session_factory() as session:
            pr = (await session.execute(select(PullRequest).where(PullRequest.id == pull_request_id))).scalar_one()
            pr.comment_id = new_id
            await session.commit()
        logger.info("pr comment posted", extra={"pr_id": pull_request_id})
    else:
        logger.warning("pr comment post failed", extra={"pr_id": pull_request_id, "status": resp.status_code})
    return {}


async def _resolve_token(session, repo: Repo) -> str | None:
    if repo.installation_id and repo.installation_id != "oauth":
        try:
            app_jwt = build_app_jwt(settings.github_app_id, settings.github_app_private_key)
            return await create_installation_token(app_jwt, repo.installation_id)
        except GithubAppError as exc:
            logger.warning("installation token failed", extra={"repo_id": repo.id, "error": str(exc)})
    token_row = (
        await session.execute(select(GithubOAuthToken).order_by(GithubOAuthToken.id.desc()))
    ).scalars().first()
    return token_row.access_token if token_row else None


# ──────────────────────────────────────────────────────────────────────
# Graph
# ──────────────────────────────────────────────────────────────────────


def _build_graph(session_factory: async_sessionmaker):
    g: StateGraph = StateGraph(PrOrchestratorState)
    g.add_node("create_run", partial(_node_create_run, session_factory))
    g.add_node("compare", partial(_node_compare, session_factory))
    g.add_node("dashboard", partial(_node_dashboard, session_factory))
    g.add_node("doc_update", partial(_node_doc_update, session_factory))
    g.add_node("persist", partial(_node_persist, session_factory))
    g.add_node("comment", partial(_node_comment, session_factory))
    g.add_node("post", partial(_node_post, session_factory))

    g.add_edge(START, "create_run")
    g.add_edge("create_run", "compare")
    g.add_edge("compare", "dashboard")
    g.add_edge("dashboard", "doc_update")
    g.add_edge("doc_update", "persist")
    g.add_edge("persist", "comment")
    g.add_edge("comment", "post")
    g.add_edge("post", END)
    return g.compile()


def _dashboard_url(base: str, pull_request_id: int) -> str:
    base = base.rstrip("/")
    return f"{base}/prs/{pull_request_id}"


async def run_pr_orchestrator(
    session_factory: async_sessionmaker,
    pull_request_id: int,
    *,
    dashboard_base_url: str | None = None,
) -> dict[str, Any]:
    base_url = dashboard_base_url or settings.public_dashboard_url
    initial: PrOrchestratorState = {
        "pull_request_id": pull_request_id,
        "dashboard_url": _dashboard_url(base_url, pull_request_id),
    }
    logger.info("pr orchestrator starting", extra={"pr_id": pull_request_id})
    graph = _build_graph(session_factory)
    pr_run_id: int | None = None
    try:
        result = await graph.ainvoke(initial)
        pr_run_id = result.get("pr_run_id")
        logger.info("pr orchestrator succeeded", extra={"pr_id": pull_request_id, "pr_run_id": pr_run_id})
        return result
    except Exception as exc:
        logger.exception("pr orchestrator failed", extra={"pr_id": pull_request_id})
        if pr_run_id is None:
            async with session_factory() as session:
                row = (
                    await session.execute(
                        select(PrAnalysisRun)
                        .where(PrAnalysisRun.pull_request_id == pull_request_id)
                        .order_by(PrAnalysisRun.id.desc())
                    )
                ).scalars().first()
                pr_run_id = row.id if row else None
        if pr_run_id is not None:
            await mark_pr_run_failed(session_factory, pr_run_id, str(exc))
        raise
