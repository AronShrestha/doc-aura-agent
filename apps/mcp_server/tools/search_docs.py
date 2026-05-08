"""Hybrid lexical+vector doc search with RRF blending."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from sqlalchemy import select, text

from aura_backend.analysis.agents.embedding import cosine_similarity, unpack_vector
from aura_backend.models import GeneratedDoc

from .._state import STATE
from ..server import mcp
from ._helpers import latest_run_id, session_factory


logger = logging.getLogger(__name__)

_RRF_K = 60.0  # Reciprocal Rank Fusion constant; bigger = flatter
_FTS_TERM_RE = __import__("re").compile(r"[A-Za-z0-9_]+")


def _sanitize_fts_query(q: str) -> str:
    """Tokenize on alnum/_ and re-quote each term with OR between.

    Empty input → empty (caller skips FTS branch).
    """
    terms = _FTS_TERM_RE.findall(q or "")
    if not terms:
        return ""
    # FTS5 OR query with double-quoted terms
    return " OR ".join(f'"{t}"' for t in terms)


@mcp.tool()
async def search_docs(query: str, repo_id: int, top_k: int = 10) -> dict[str, Any]:
    """Search living documentation using FTS5 lexical + Qwen-Embedding vector cosine.

    Args:
        query: free-form natural-language query
        repo_id: ID of the repository to search within
        top_k: number of merged results to return (default 10)

    Returns:
        ``{"results": [{slug_path, title, snippet, score, source: 'fts'|'vector'|'rrf'}]}``
    """
    factory = session_factory()
    async with factory() as session:
        run_id = await latest_run_id(session, repo_id)
        if run_id is None:
            return {"error": "no_runs_for_repo", "results": []}

        # FTS5 ranking. Sanitize the query so special FTS5 characters
        # (parentheses, quotes, NEAR keyword) don't blow up the parser.
        fts_query = _sanitize_fts_query(query)
        fts_hits: list[tuple[int, float, GeneratedDoc]] = []
        if fts_query:
            try:
                rows = (
                    await session.execute(
                        text(
                            """
                            SELECT g.id, bm25(docs_fts) AS score
                            FROM docs_fts
                            JOIN generated_docs g ON g.id = docs_fts.rowid
                            WHERE docs_fts MATCH :q AND g.run_id = :run_id
                            ORDER BY bm25(docs_fts)
                            LIMIT :limit
                            """
                        ),
                        {"q": fts_query, "run_id": run_id, "limit": max(top_k * 4, 20)},
                    )
                ).all()
                id_to_score = {r.id: r.score for r in rows}
                if id_to_score:
                    docs = (
                        await session.execute(
                            select(GeneratedDoc).where(GeneratedDoc.id.in_(list(id_to_score)))
                        )
                    ).scalars().all()
                    fts_hits = [(d.id, id_to_score[d.id], d) for d in docs]
            except Exception as exc:
                logger.warning("fts query failed", extra={"error": str(exc)})

        # Vector search
        vector_hits: list[tuple[int, float, GeneratedDoc]] = []
        if STATE.embedder is not None:
            try:
                emb = await STATE.embedder.embed([query])
                if emb.vectors:
                    qvec = emb.vectors[0]
                    rows = (
                        await session.execute(
                            select(GeneratedDoc).where(
                                GeneratedDoc.run_id == run_id,
                                GeneratedDoc.embedding.is_not(None),
                            )
                        )
                    ).scalars().all()
                    if rows:
                        mat = np.stack(
                            [unpack_vector(r.embedding, r.embedding_dim or 0) for r in rows]
                        )
                        # Pad query/matrix to same dim
                        d = mat.shape[1]
                        if qvec.shape[0] != d:
                            if qvec.shape[0] > d:
                                qvec = qvec[:d]
                            else:
                                qvec = np.pad(qvec, (0, d - qvec.shape[0]))
                        sims = cosine_similarity(qvec, mat)
                        order = np.argsort(-sims)[: max(top_k * 4, 20)]
                        vector_hits = [(rows[i].id, float(sims[i]), rows[i]) for i in order]
            except Exception as exc:
                logger.warning("vector search failed", extra={"error": str(exc)})

        # RRF merge: score = sum(1 / (k + rank))
        ranks: dict[int, dict[str, Any]] = {}
        for rank, (doc_id, score, doc) in enumerate(fts_hits):
            ranks.setdefault(doc_id, {"doc": doc, "fts_rank": None, "vec_rank": None, "score": 0.0})
            ranks[doc_id]["fts_rank"] = rank
            ranks[doc_id]["score"] += 1.0 / (_RRF_K + rank + 1)
        for rank, (doc_id, score, doc) in enumerate(vector_hits):
            ranks.setdefault(doc_id, {"doc": doc, "fts_rank": None, "vec_rank": None, "score": 0.0})
            ranks[doc_id]["vec_rank"] = rank
            ranks[doc_id]["score"] += 1.0 / (_RRF_K + rank + 1)

        merged = sorted(ranks.values(), key=lambda r: -r["score"])[:top_k]
        results = []
        for r in merged:
            doc = r["doc"]
            snippet = (doc.content_md or "").strip().splitlines()
            preview = "\n".join(snippet[:5])[:400]
            sources = []
            if r["fts_rank"] is not None:
                sources.append("fts")
            if r["vec_rank"] is not None:
                sources.append("vector")
            results.append(
                {
                    "artifact_id": doc.artifact_id,
                    "slug_path": doc.slug_path,
                    "title": doc.title,
                    "snippet": preview,
                    "score": round(r["score"], 4),
                    "sources": sources,
                }
            )

        return {"query": query, "repo_id": repo_id, "run_id": run_id, "results": results}
