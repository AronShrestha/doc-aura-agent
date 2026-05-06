from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


SKIP_PARTS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
}


def stable_artifact_id(repo_id: int, category: str, canonical_locator: str) -> str:
    return hashlib.sha256(f"{repo_id}:{category}:{canonical_locator}".encode("utf-8")).hexdigest()[:16]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_read(path: Path, max_bytes: int = 750_000) -> str:
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="ignore")


def should_skip(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    return any(part in SKIP_PARTS for part in rel.parts)


def language_for_path(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        return "javascript"
    if suffix == ".md":
        return "markdown"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix == ".json":
        return "json"
    if suffix == ".toml":
        return "toml"
    if name.startswith(".env"):
        return "env"
    if name in {"dockerfile"} or name.startswith("dockerfile."):
        return "dockerfile"
    if suffix in {".ini", ".cfg"}:
        return "config"
    return "other"


def slugify(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or fallback


def node_to_source(value: Any) -> str | None:
    import ast

    if value is None:
        return None
    try:
        return ast.unparse(value)
    except Exception:
        return None


def literal_string(value: Any) -> str | None:
    import ast

    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    if isinstance(value, ast.JoinedStr):
        parts: list[str] = []
        for item in value.values:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                parts.append(item.value)
            else:
                return None
        return "".join(parts)
    return None
