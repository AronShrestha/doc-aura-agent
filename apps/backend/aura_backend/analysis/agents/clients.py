from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Protocol

import httpx


logger = logging.getLogger(__name__)

class TextModelClient(Protocol):
    async def complete(self, messages: list[dict[str, Any]], *, max_tokens: int | None = None, temperature: float = 0.2) -> str:
        logger.info("llm request started", extra={"event": "llm_request"})
        ...


class VisionModelClient(Protocol):
    async def describe_image(self, image_path: Path, prompt: str) -> str:
        ...


class OpenAIChatClient:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout_seconds: int = 90, max_tokens: int = 4096):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens

    async def complete(self, messages: list[dict[str, Any]], *, max_tokens: int | None = None, temperature: float = 0.2) -> str:
        import asyncio
        import json
        import os

        # Demo replay mode — never hit the network. Returns a deterministic
        # placeholder so the rest of the pipeline (verifier, persist) still
        # exercises end-to-end. Use AURA_DEMO_MODE=replay during stage demos
        # if the LLM endpoint is flaky.
        if os.getenv("AURA_DEMO_MODE", "").lower() == "replay":
            logger.info("llm replay mode", extra={"event": "llm_replay"})
            return _replay_response(messages)

        # Estimate token usage and clamp max_tokens so input + output fits the
        # model's context window. vLLM returns 400 if (prompt_tokens +
        # max_tokens) > max_model_len.
        approx_input_chars = sum(len(str(m.get("content", ""))) for m in messages)
        approx_input_tokens = approx_input_chars // 4  # rough heuristic
        ctx_window = int(os.getenv("LLM_MAX_CONTEXT", "32768"))
        head_room = max(256, ctx_window - approx_input_tokens - 256)
        chosen_max = max_tokens or self.max_tokens
        if chosen_max > head_room:
            logger.warning(
                "clamping max_tokens to fit context window",
                extra={
                    "event": "llm_clamp",
                    "input_tokens_est": approx_input_tokens,
                    "ctx_window": ctx_window,
                    "from": chosen_max,
                    "to": head_room,
                },
            )
            chosen_max = head_room

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": chosen_max,
            "stream": True,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Granular timeouts: read = max idle gap between chunks (not total
        # response time). Streaming means slow generation no longer trips a
        # whole-response timeout.
        timeout = httpx.Timeout(
            connect=float(os.getenv("LLM_CONNECT_TIMEOUT", "30")),
            read=float(self.timeout_seconds),
            write=30.0,
            pool=float(os.getenv("LLM_POOL_TIMEOUT", "30")),
        )
        limits = httpx.Limits(
            max_connections=int(os.getenv("LLM_MAX_CONNECTIONS", "64")),
            max_keepalive_connections=int(os.getenv("LLM_KEEPALIVE_CONNECTIONS", "32")),
        )

        max_attempts = int(os.getenv("LLM_MAX_ATTEMPTS", "6"))
        backoff = float(os.getenv("LLM_BACKOFF_BASE", "1.5"))
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as resp:
                        if resp.status_code >= 400:
                            body = (await resp.aread()).decode("utf-8", "replace")
                            if resp.status_code >= 500 or resp.status_code == 429:
                                logger.warning(
                                    "llm transient error",
                                    extra={"event": "llm_retry", "status": resp.status_code, "attempt": attempt, "body": body[:500]},
                                )
                                if attempt < max_attempts:
                                    await asyncio.sleep(backoff * attempt)
                                    continue
                            # 400 from vLLM most often = unknown model OR
                            # context overflow. Surface body in the exception
                            # itself so callers see why instead of just '400'.
                            logger.error(
                                "llm request failed",
                                extra={
                                    "event": "llm_error",
                                    "status": resp.status_code,
                                    "model": self.model,
                                    "url": f"{self.base_url}/chat/completions",
                                    "input_tokens_est": approx_input_tokens,
                                    "max_tokens": chosen_max,
                                    "body": body[:2000],
                                },
                            )
                            raise RuntimeError(
                                f"llm_{resp.status_code}: model={self.model!r} "
                                f"input_tokens~{approx_input_tokens} max_tokens={chosen_max} "
                                f"body={body[:500]}"
                            )

                        chunks: list[str] = []
                        async for line in resp.aiter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                            except json.JSONDecodeError:
                                logger.warning(
                                    "llm stream malformed chunk",
                                    extra={"event": "llm_stream_parse_error", "line": data_str[:200]},
                                )
                                continue
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            delta = choices[0].get("delta") or {}
                            piece = delta.get("content")
                            if piece:
                                chunks.append(piece)
                logger.info("llm request succeeded", extra={"event": "llm_response", "attempt": attempt})
                return "".join(chunks)
            except (
                httpx.TimeoutException,   # ConnectTimeout, ReadTimeout, WriteTimeout, PoolTimeout
                httpx.NetworkError,       # ConnectError, ReadError, WriteError, CloseError
                httpx.ProtocolError,      # RemoteProtocolError, LocalProtocolError
            ) as exc:
                last_exc = exc
                # exponential backoff with jitter so concurrent retries don't synchronize
                import random
                delay = (backoff ** attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "llm network error",
                    extra={
                        "event": "llm_retry",
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "next_delay_s": round(delay, 2),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                if attempt < max_attempts:
                    await asyncio.sleep(delay)
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("llm_request_failed")


class OpenAIVisionClient(OpenAIChatClient):
    async def describe_image(self, image_path: Path, prompt: str) -> str:
        logger.info("vlm image request started", extra={"event": "vlm_request"})
        data = image_path.read_bytes()
        mime = _mime_for_path(image_path)
        encoded = base64.b64encode(data).decode("ascii")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ],
            }
        ]
        return await self.complete(messages, max_tokens=self.max_tokens, temperature=0.1)


class DisabledVisionClient:
    async def describe_image(self, image_path: Path, prompt: str) -> str:
        raise RuntimeError("vlm_disabled")


def _replay_response(messages: list[dict[str, Any]]) -> str:
    """Deterministic placeholder for demo replay mode.

    If the system prompt asks for JSON (verifier path), return a minimal
    pass-OK JSON. Otherwise return Markdown with a single plausible
    verified citation so the pipeline persists doc rows successfully.
    """
    system = next((m["content"] for m in messages if m.get("role") == "system"), "")
    if "JSON" in system or "json" in system:
        return (
            '{"passed": true, "citation_coverage": 0.9, '
            '"unsupported_claims": 0, "section_completeness": 1.0, "issues": []}'
        )
    return (
        "## Overview\n\n"
        "_Replay mode — generated locally without LLM call._\n\n"
        "This artifact is documented from extracted facts only "
        "[verified: replay/replay.py:L1-L1].\n"
    )


def _mime_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".gif":
        return "image/gif"
    return "image/png"
