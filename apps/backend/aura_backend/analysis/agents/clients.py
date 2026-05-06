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

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or self.max_tokens,
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
                        logger.error(
                            "llm request failed",
                            extra={"event": "llm_error", "status": resp.status_code, "body": resp.text[:2000]},
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


def _mime_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".gif":
        return "image/gif"
    return "image/png"
