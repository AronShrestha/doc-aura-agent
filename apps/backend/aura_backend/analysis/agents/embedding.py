"""Qwen-Embedding client over a vLLM-style ``/v1/embeddings`` endpoint.

Configured via env vars (mirroring ``clients.OpenAIChatClient``):

- ``EMBEDDING_BASE_URL``  — defaults to ``LLM_BASE_URL`` if unset.
- ``EMBEDDING_MODEL``     — defaults to ``Qwen/Qwen3-Embedding-8B``.
- ``EMBEDDING_API_KEY``   — optional bearer token.
- ``EMBEDDING_DIM``       — declared output dim; persisted alongside vector.

The client batches requests (default 64 inputs per call) and returns the
embeddings as ``np.float32`` arrays so they can be packed into the
``GeneratedDoc.embedding`` BLOB column with ``arr.tobytes()``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

import httpx
import numpy as np


logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    vectors: list[np.ndarray]  # one float32 ndarray per input
    model: str
    dim: int


class QwenEmbedder:
    """Thin async client for an OpenAI-compatible ``/v1/embeddings`` endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: int = 60,
        batch_size: int = 64,
    ) -> None:
        self.base_url = (base_url or os.getenv("EMBEDDING_BASE_URL") or os.getenv("LLM_BASE_URL", "")).rstrip("/")
        self.model = model or os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")
        self.api_key = api_key or os.getenv("EMBEDDING_API_KEY", "") or os.getenv("LLM_API_KEY", "")
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], model=self.model, dim=0)
        if not self.base_url:
            raise RuntimeError(
                "embedding_base_url_unset — set EMBEDDING_BASE_URL or LLM_BASE_URL"
            )

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        all_vectors: list[np.ndarray] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i : i + self.batch_size]
                resp = await client.post(
                    f"{self.base_url}/embeddings",
                    headers=headers,
                    json={"model": self.model, "input": batch},
                )
                resp.raise_for_status()
                data = resp.json()
                for item in data["data"]:
                    vec = np.asarray(item["embedding"], dtype=np.float32)
                    all_vectors.append(vec)

        dim = int(all_vectors[0].shape[0]) if all_vectors else 0
        return EmbeddingResult(vectors=all_vectors, model=self.model, dim=dim)


def cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine sim between a (D,) query and an (N, D) matrix."""
    q_norm = np.linalg.norm(query)
    if q_norm == 0:
        return np.zeros(matrix.shape[0], dtype=np.float32)
    m_norms = np.linalg.norm(matrix, axis=1)
    m_norms = np.where(m_norms == 0, 1.0, m_norms)
    return (matrix @ query) / (m_norms * q_norm)


def pack_vector(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def unpack_vector(blob: bytes, dim: int) -> np.ndarray:
    arr = np.frombuffer(blob, dtype=np.float32)
    if dim and arr.size != dim:
        return arr[:dim] if arr.size > dim else np.pad(arr, (0, dim - arr.size))
    return arr
