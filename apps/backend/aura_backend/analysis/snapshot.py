from __future__ import annotations

import ast
import json
import logging
import tomllib
from collections import Counter
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover - dependency should be present in runtime
    yaml = None

from .types import RepoSnapshot, SourceFile
from .utils import language_for_path, safe_read, sha256_text, should_skip


logger = logging.getLogger(__name__)


def build_snapshot(root: Path, repo_id: int, repo_sha: str) -> RepoSnapshot:
    files: list[SourceFile] = []
    framework_hints: Counter[str] = Counter()

    for path in sorted(root.rglob("*")):
        if not path.is_file() or should_skip(path, root):
            continue
        rel = path.relative_to(root).as_posix()
        language = language_for_path(path)
        if language == "other" and path.stat().st_size > 400_000:
            continue
        text = safe_read(path)
        source = SourceFile(
            path=rel,
            language=language,
            loc=len(text.splitlines()),
            source_hash=sha256_text(text),
            text=text,
        )
        _inspect_file(source, framework_hints)
        files.append(source)

    snapshot = RepoSnapshot(root=root, repo_id=repo_id, repo_sha=repo_sha, files=files, frameworks=sorted(framework_hints))
    logger.info(
        "repo snapshot complete",
        extra={"repo_id": repo_id, "event": "snapshot_complete"},
    )
    return snapshot


def _inspect_file(source: SourceFile, framework_hints: Counter[str]) -> None:
    if source.language == "python":
        _inspect_python(source, framework_hints)
    elif source.path.endswith("package.json"):
        _inspect_package_json(source, framework_hints)
    elif source.path.endswith("pyproject.toml"):
        _inspect_pyproject(source, framework_hints)
    elif source.language == "yaml":
        _inspect_yaml(source)
    elif source.language == "markdown":
        source.top_level_symbols = [
            line.lstrip("# ").strip()
            for line in source.text.splitlines()
            if line.startswith("#")
        ][:50]


def _inspect_python(source: SourceFile, framework_hints: Counter[str]) -> None:
    try:
        tree = ast.parse(source.text or "", filename=source.path)
    except SyntaxError as exc:
        source.parse_errors.append(f"{exc.msg} at line {exc.lineno}")
        return
    except Exception as exc:
        source.parse_errors.append(str(exc))
        return

    symbols: list[str] = []
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append("." * node.level + (node.module or ""))

    source.top_level_symbols = symbols
    source.imports = imports
    joined = "\n".join(imports) + "\n" + source.text[:8000]
    if "fastapi" in joined or "APIRouter" in joined:
        framework_hints["fastapi"] += 1
    if "flask" in joined or "Blueprint(" in joined:
        framework_hints["flask"] += 1
    if "BaseModel" in joined or "pydantic" in joined:
        framework_hints["pydantic"] += 1
    if "sqlalchemy" in joined or "DeclarativeBase" in joined or "mapped_column" in joined:
        framework_hints["sqlalchemy"] += 1
    if "pytest" in joined or source.path.startswith("tests/"):
        framework_hints["pytest"] += 1


def _inspect_package_json(source: SourceFile, framework_hints: Counter[str]) -> None:
    try:
        data = json.loads(source.text or "{}")
    except Exception as exc:
        source.parse_errors.append(str(exc))
        return
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    source.top_level_symbols = sorted((data.get("scripts") or {}).keys())
    if "vite" in deps or "vite" in data.get("scripts", {}).get("dev", ""):
        framework_hints["vite"] += 1
    if "react" in deps:
        framework_hints["react"] += 1


def _inspect_pyproject(source: SourceFile, framework_hints: Counter[str]) -> None:
    try:
        data = tomllib.loads(source.text or "")
    except Exception as exc:
        source.parse_errors.append(str(exc))
        return
    deps = " ".join(data.get("project", {}).get("dependencies", []))
    if "fastapi" in deps:
        framework_hints["fastapi"] += 1
    if "pytest" in str(data):
        framework_hints["pytest"] += 1


def _inspect_yaml(source: SourceFile) -> None:
    if yaml is None:
        return
    try:
        yaml.safe_load(source.text or "")
    except Exception as exc:
        source.parse_errors.append(str(exc))
