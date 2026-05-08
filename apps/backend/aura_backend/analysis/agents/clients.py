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
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        max_attempts = 4
        backoff = 2.0
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                    if resp.status_code >= 500 or resp.status_code == 429:
                        logger.warning(
                            "llm transient error",
                            extra={"event": "llm_retry", "status": resp.status_code, "attempt": attempt, "body": resp.text[:500]},
                        )
                        if attempt < max_attempts:
                            await asyncio.sleep(backoff * attempt)
                            continue
                    if resp.status_code >= 400:
                        body = resp.text
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
                    resp.raise_for_status()
                    data = resp.json()
                logger.info("llm request succeeded", extra={"event": "llm_response", "attempt": attempt})
                return data["choices"][0]["message"]["content"]
            except (httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                logger.warning("llm network error", extra={"event": "llm_retry", "attempt": attempt, "error": str(exc)})
                if attempt < max_attempts:
                    await asyncio.sleep(backoff * attempt)
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
