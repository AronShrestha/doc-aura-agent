from __future__ import annotations

import json
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from .types import GeneratedDocDraft, RepoSnapshot


logger = logging.getLogger(__name__)

DOC_ROOT = Path(".aura/docs")


def write_docs(root: Path, docs: list[GeneratedDocDraft], manifest: dict[str, Any]) -> None:
    logger.info("writing generated docs", extra={"event": "docs_write_started"})
    staging = root / ".aura" / ".docs-staging"
    final_root = root / DOC_ROOT
    if staging.exists():
        import shutil

        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        rel = _doc_relative_path(doc.slug_path)
        target = staging / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(doc.content_md, encoding="utf-8")
    manifest_target = staging / ".aura-manifest.json"
    manifest_target.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    if final_root.exists():
        import shutil

        shutil.rmtree(final_root)
    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(final_root)
    logger.info("generated docs published", extra={"event": "docs_write_complete"})


def build_manifest(
    snapshot: RepoSnapshot,
    docs: list[GeneratedDocDraft],
    *,
    codebase_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "repo_id": snapshot.repo_id,
        "repo_sha": snapshot.repo_sha,
        "generated_at": datetime.now(UTC).isoformat(),
        "codebase_profile": codebase_profile or {},
        "tree": build_doc_tree(docs),
        "docs": {
            doc.artifact_id: {
                "path": doc.slug_path,
                "category": doc.category,
                "title": doc.title,
                "content_hash": doc.content_hash,
                "source_files": doc.source_files,
            }
            for doc in docs
        },
    }


def build_doc_tree(docs: list[GeneratedDocDraft]) -> list[dict[str, Any]]:
    """Hierarchical tree of docs grouped by their slug path under .aura/docs/.

    Folder nodes have ``label`` + ``children``; leaf nodes have ``label``,
    ``path``, ``doc_id``, ``title``.
    """
    root: dict[str, Any] = {"_children": {}, "_leaves": []}
    for doc in docs:
        if doc.category == "index":
            continue
        rel = doc.slug_path.removeprefix(".aura/docs/")
        parts = rel.split("/")
        node = root
        for segment in parts[:-1]:
            child = node["_children"].setdefault(segment, {"_children": {}, "_leaves": []})
            node = child
        node["_leaves"].append(doc)

    def render(node: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for leaf in sorted(node["_leaves"], key=lambda d: d.title.lower()):
            out.append(
                {
                    "label": leaf.title,
                    "path": leaf.slug_path,
                    "doc_id": leaf.artifact_id,
                    "title": leaf.title,
                }
            )
        for name, child in sorted(node["_children"].items()):
            out.append({"label": name, "children": render(child)})
        return out

    return render(root)


def _doc_relative_path(path: str) -> Path:
    return Path(path.removeprefix(".aura/docs/"))
