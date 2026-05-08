"""Docs chat agent — answers user questions grounded in the repo's generated docs.

Pipeline:
  1. Embed the user message (Qwen embeddings).
  2. Rank GeneratedDoc rows by cosine similarity over their stored embeddings.
     Falls back to lowercase-substring keyword scoring when no docs have
     embeddings (matches the heuristic in routes/analysis.docs_search).
  3. Build a system+context prompt from the top-K docs and call the LLM.
  4. Strip [[doc:<artifact_id>]] navigation tokens from the answer; resolve
     them against the docs list to produce DocChatLink objects.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

import numpy as np

from ...models import GeneratedDoc
from ...schemas import DocChatHistoryItem, DocChatLink, DocChatRequest, DocChatResponse
from .clients import TextModelClient
from .embedding import QwenEmbedder, cosine_similarity, unpack_vector


logger = logging.getLogger(__name__)


TOP_K = 5
MAX_DOC_CHARS = 1500
MAX_HISTORY_TURNS = 6
MAX_HEADINGS_PER_DOC = 12
# Token forms accepted from the model:
#   [[doc:<doc_id>]]                          → page-level link
#   [[doc:<doc_id>#<anchor-slug>]]            → page + section anchor
NAV_TOKEN_RE = re.compile(r"\[\[doc:([^\]\s#]+)(?:#([^\]\s]+))?\]\]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


async def answer_docs_question(
    llm: TextModelClient,
    req: DocChatRequest,
    docs: list[GeneratedDoc],
) -> DocChatResponse:
    if not docs:
        return DocChatResponse(
            answer="No documentation has been generated for this repo yet.",
            links=[],
        )

    ranked = await _rank_docs(req.message, docs)
    top_docs = ranked[:TOP_K]

    active_doc = next((d for d in docs if d.artifact_id == req.active_doc_id), None)
    messages = _build_messages(req, top_docs, active_doc)

    raw_answer = await llm.complete(messages, max_tokens=800, temperature=0.3)
    answer, links = _extract_links(raw_answer, docs)
    return DocChatResponse(answer=answer, links=links)


async def _rank_docs(query: str, docs: list[GeneratedDoc]) -> list[GeneratedDoc]:
    embedded = [d for d in docs if d.embedding and d.embedding_dim]
    if not embedded:
        logger.info("docs_chat keyword fallback", extra={"event": "docs_chat_keyword_fallback"})
        return _keyword_rank(query, docs)

    try:
        embedder = QwenEmbedder()
        result = await embedder.embed([query])
    except Exception:
        logger.exception("docs_chat embedding failed; falling back to keyword scoring")
        return _keyword_rank(query, docs)

    if not result.vectors:
        return _keyword_rank(query, docs)

    q_vec = result.vectors[0]
    target_dim = int(q_vec.shape[0])
    matrix_rows: list[np.ndarray] = []
    matrix_docs: list[GeneratedDoc] = []
    for d in embedded:
        vec = unpack_vector(d.embedding, d.embedding_dim or target_dim)
        if vec.shape[0] != target_dim:
            continue
        matrix_rows.append(vec)
        matrix_docs.append(d)

    if not matrix_rows:
        return _keyword_rank(query, docs)

    matrix = np.vstack(matrix_rows)
    scores = cosine_similarity(q_vec, matrix)
    order = np.argsort(-scores)
    return [matrix_docs[int(i)] for i in order]


def _keyword_rank(query: str, docs: list[GeneratedDoc]) -> list[GeneratedDoc]:
    q = query.lower().strip()
    if not q:
        return list(docs)
    scored: list[tuple[int, GeneratedDoc]] = []
    for d in docs:
        score = 0
        if q in (d.title or "").lower():
            score += 2
        if q in (d.content_md or "").lower():
            score += 1
        if score:
            scored.append((score, d))
    scored.sort(key=lambda t: t[0], reverse=True)
    if scored:
        return [d for _, d in scored]
    return list(docs)


def _build_messages(
    req: DocChatRequest,
    top_docs: list[GeneratedDoc],
    active_doc: GeneratedDoc | None,
) -> list[dict[str, str]]:
    context = "\n\n---\n\n".join(_format_doc(d) for d in top_docs) or "(no relevant docs found)"
    active_title = active_doc.title if active_doc else "none"
    system = (
        "You are a documentation assistant for a code repository. Answer the user's "
        "question using only the provided documentation context. The context is drawn "
        "from across the entire repo's docs, not just the page the user is currently "
        "viewing. When you reference a specific doc or section, embed a navigation "
        "token immediately after the relevant phrase. Token forms:\n"
        "  [[doc:<doc_id>]]                  → links to the doc page\n"
        "  [[doc:<doc_id>#<anchor-slug>]]    → links directly to a heading inside the doc\n"
        "Use the doc_id and anchor-slug values shown in the context (each doc lists its "
        "available headings as `- <Heading Text> :: <anchor-slug>`). Prefer section-level "
        "tokens whenever a specific heading answers the question — these render as "
        "clickable buttons for the user. If the answer is not in the context, say so "
        "plainly. Be concise and cite at most 3 sources.\n\n"
        f"Active doc: {active_title}\n\n"
        f"Context:\n{context}"
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for turn in _trim_history(req.history):
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": req.message})
    return messages


def _format_doc(doc: GeneratedDoc) -> str:
    body = (doc.content_md or "").strip()
    if len(body) > MAX_DOC_CHARS:
        body = body[:MAX_DOC_CHARS].rstrip() + "…"
    headings = _extract_headings(doc.content_md or "")
    if headings:
        heading_block = "\n".join(f"  - {title} :: {slug}" for title, slug in headings)
        heading_section = f"Headings:\n{heading_block}\n"
    else:
        heading_section = ""
    return f"[doc_id: {doc.artifact_id}] {doc.title}\n{heading_section}{body}"


def _extract_headings(md: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in HEADING_RE.finditer(md):
        title = match.group(2).strip()
        slug = _slugify(title)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append((title, slug))
        if len(out) >= MAX_HEADINGS_PER_DOC:
            break
    return out


def _slugify(text: str) -> str:
    """Mirror the frontend slugify in DocsDashboard.jsx so anchors line up."""
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def _trim_history(history: Iterable[DocChatHistoryItem]) -> list[DocChatHistoryItem]:
    items = list(history)
    if len(items) <= MAX_HISTORY_TURNS:
        return items
    return items[-MAX_HISTORY_TURNS:]


def _extract_links(answer: str, docs: list[GeneratedDoc]) -> tuple[str, list[DocChatLink]]:
    """Replace [[doc:..]] tokens with inline markdown links using the
    ``aura-doc:`` URL scheme. The frontend intercepts that scheme and renders
    each link as a navigation pill button. We also return the deduped list of
    links for any caller that wants the structured metadata.
    """
    by_id = {d.artifact_id: d for d in docs}
    headings_by_doc: dict[str, dict[str, str]] = {}
    seen: set[tuple[str, str | None]] = set()
    links: list[DocChatLink] = []

    def replace(match: re.Match[str]) -> str:
        doc_id = match.group(1)
        anchor = match.group(2)
        doc = by_id.get(doc_id)
        if not doc:
            return ""
        section_title: str | None = None
        if anchor:
            heading_map = headings_by_doc.get(doc_id)
            if heading_map is None:
                heading_map = {slug: title for title, slug in _extract_headings(doc.content_md or "")}
                headings_by_doc[doc_id] = heading_map
            if anchor in heading_map:
                section_title = heading_map[anchor]
            else:
                anchor = None  # LLM hallucinated a slug — degrade to page link.

        label = section_title or doc.title
        href_target = f"{doc_id}#{anchor}" if anchor else doc_id
        # Sanitize label for markdown link text (avoid stray ] / [ closing the link).
        safe_label = label.replace("[", "(").replace("]", ")")

        key = (doc_id, anchor)
        if key not in seen:
            seen.add(key)
            links.append(
                DocChatLink(
                    doc_id=doc_id,
                    title=doc.title,
                    anchor=anchor,
                    section_title=section_title,
                )
            )
        return f"[{safe_label}](aura-doc:{href_target})"

    cleaned = NAV_TOKEN_RE.sub(replace, answer)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, links
