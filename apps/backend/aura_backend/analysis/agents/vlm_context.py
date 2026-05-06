from __future__ import annotations

import logging
from pathlib import Path

from .clients import VisionModelClient
from .context import discover_media_files
from .models import VisualContext
from ..types import RepoSnapshot


logger = logging.getLogger(__name__)


async def run_vlm_context_agent(snapshot: RepoSnapshot, vlm_client: VisionModelClient | None, enabled: bool) -> list[VisualContext]:
    if not enabled:
        logger.info("vlm disabled; skipping media inspection", extra={"repo_id": snapshot.repo_id, "agent": "vlm_context"})
        return []
    if vlm_client is None:
        raise RuntimeError("vlm_enabled_without_client")
    contexts: list[VisualContext] = []
    for path in discover_media_files(snapshot):
        rel = path.relative_to(snapshot.root).as_posix()
        logger.info("vlm inspecting media", extra={"repo_id": snapshot.repo_id, "agent": "vlm_context"})
        prompt = (
            "You are Aura's VLM Context Agent. Inspect this repository media asset. "
            "Describe what it shows, identify if it is useful for architecture, UI, setup, or usage documentation, "
            "and do not infer code behavior from the image. Return concise JSON with keys: "
            "description, documentation_relevance, confidence."
        )
        raw = await vlm_client.describe_image(path, prompt)
        contexts.append(_visual_context_from_raw(rel, path, raw))
    logger.info("vlm media inspection complete", extra={"repo_id": snapshot.repo_id, "agent": "vlm_context"})
    return contexts


def _visual_context_from_raw(rel: str, path: Path, raw: str) -> VisualContext:
    import json

    try:
        data = json.loads(raw.strip())
    except Exception:
        data = {"description": raw.strip(), "documentation_relevance": "unknown", "confidence": 0.5}
    return VisualContext(
        path=rel,
        media_type=path.suffix.lower().lstrip(".") or "image",
        description=str(data.get("description", "")).strip(),
        documentation_relevance=str(data.get("documentation_relevance", "")).strip(),
        confidence=float(data.get("confidence", 0.5) or 0.5),
    )
