from __future__ import annotations

import ast
import json
import logging
import re
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

from .types import ExtractedArtifact, ExtractedEdge, RepoSnapshot, SourceFile
from .graph import add_service_flow_artifacts
from .ingestion_bridge import (
    apply_semantic_hashes,
    extract_js_ts_artifacts,
    parse_all as _parse_all_with_treesitter,
)
from .utils import literal_string, node_to_source, slugify, stable_artifact_id


logger = logging.getLogger(__name__)

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
EDGE_KINDS = {"imports", "calls", "handles_endpoint", "uses_model", "reads_env", "configured_by"}


def extract_repo(snapshot: RepoSnapshot) -> tuple[list[ExtractedArtifact], list[ExtractedEdge], dict[str, Any]]:
    logger.info("extractors started", extra={"repo_id": snapshot.repo_id, "event": "extract_started"})
    artifacts: list[ExtractedArtifact] = []
    edges: list[ExtractedEdge] = []
    by_locator: dict[str, str] = {}
    module_by_path: dict[str, str] = {}
    function_by_simple_name: dict[str, list[str]] = defaultdict(list)

    for source in snapshot.files:
        if source.language == "python":
            module = _module_artifact(snapshot, source)
            artifacts.append(module)
            by_locator[module.canonical_locator] = module.artifact_id
            module_by_path[source.path] = module.artifact_id

    for source in snapshot.files:
        if source.language == "python":
            py_artifacts, py_edges = _extract_python(snapshot, source, module_by_path.get(source.path))
            artifacts.extend(py_artifacts)
            edges.extend(py_edges)
            for artifact in py_artifacts:
                by_locator[artifact.canonical_locator] = artifact.artifact_id
                if artifact.category == "function":
                    function_by_simple_name[artifact.payload.get("simple_name", artifact.name)].append(artifact.artifact_id)
        elif _is_config_source(source):
            artifacts.extend(_extract_config(snapshot, source))
        elif source.language == "markdown" and _is_human_doc(source.path):
            artifacts.append(_human_doc_artifact(snapshot, source))

    edges.extend(_import_edges(snapshot, artifacts, module_by_path))
    edges.extend(_resolved_call_edges(artifacts, function_by_simple_name))

    # Tree-sitter pass: one parse, two consumers.
    parsed_symbols = _parse_all_with_treesitter(snapshot)
    apply_semantic_hashes(artifacts, snapshot, parsed=parsed_symbols)
    ts_artifacts, ts_edges = extract_js_ts_artifacts(snapshot, parsed=parsed_symbols)
    artifacts.extend(ts_artifacts)
    edges.extend(ts_edges)

    artifacts, edges = add_service_flow_artifacts(snapshot, _dedupe_artifacts(artifacts), _dedupe_edges(edges))
    edges = _dedupe_edges(edges)
    summary = _summary(snapshot, artifacts, edges)
    logger.info("extractors complete", extra={"repo_id": snapshot.repo_id, "event": "extract_complete"})
    return _dedupe_artifacts(artifacts), edges, summary


def _module_name(path: str) -> str:
    return path.removesuffix(".py").replace("/", ".")


def _module_artifact(snapshot: RepoSnapshot, source: SourceFile) -> ExtractedArtifact:
    name = _module_name(source.path)
    aid = stable_artifact_id(snapshot.repo_id, "module", name)
    return ExtractedArtifact(
        artifact_id=aid,
        category="module",
        name=name,
        canonical_locator=name,
        source_file=source.path,
        source_line_start=1,
        source_line_end=max(1, source.loc),
        payload={
            "language": "python",
            "loc": source.loc,
            "source_hash": source.source_hash,
            "imports": source.imports,
            "exports": source.top_level_symbols,
            "parse_errors": source.parse_errors,
        },
    )


def _extract_python(snapshot: RepoSnapshot, source: SourceFile, module_id: str | None) -> tuple[list[ExtractedArtifact], list[ExtractedEdge]]:
    artifacts: list[ExtractedArtifact] = []
    edges: list[ExtractedEdge] = []
    try:
        tree = ast.parse(source.text or "", filename=source.path)
    except Exception:
        return artifacts, edges

    module_name = _module_name(source.path)
    router_prefixes = _router_prefixes(tree)
    include_prefixes = _include_prefixes(tree)
    class_stack: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            model = _model_artifact(snapshot, source, module_name, node)
            if model:
                artifacts.append(model)
                if module_id:
                    edges.append(ExtractedEdge(module_id, model.artifact_id, "uses_model"))

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_stack.append(node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    artifact = _function_artifact(snapshot, source, module_name, item, owner=node.name)
                    artifacts.append(artifact)
                    if module_id:
                        edges.append(ExtractedEdge(module_id, artifact.artifact_id, "calls"))
            class_stack.pop()
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            artifact = _function_artifact(snapshot, source, module_name, node)
            artifacts.append(artifact)
            if module_id:
                edges.append(ExtractedEdge(module_id, artifact.artifact_id, "calls"))

    function_by_line = {a.source_line_start: a for a in artifacts if a.category == "function"}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        function = function_by_line.get(getattr(node, "lineno", None))
        for route in _route_decorators(node, router_prefixes, include_prefixes):
            endpoint = _endpoint_artifact(snapshot, source, module_name, node, route)
            artifacts.append(endpoint)
            if function:
                edges.append(ExtractedEdge(endpoint.artifact_id, function.artifact_id, "handles_endpoint"))
            for dep in endpoint.payload.get("auth_dependencies", []):
                dep_id = stable_artifact_id(snapshot.repo_id, "function", f"{module_name}.{dep}")
                edges.append(ExtractedEdge(endpoint.artifact_id, dep_id, "calls"))
        for var, line in _env_reads(node):
            env = _env_artifact(snapshot, source, var, line)
            artifacts.append(env)
            if function:
                edges.append(ExtractedEdge(function.artifact_id, env.artifact_id, "reads_env"))

    for var, line in _module_env_reads(tree):
        artifacts.append(_env_artifact(snapshot, source, var, line))

    return artifacts, edges


def _router_prefixes(tree: ast.AST) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        if _call_name(node.value.func).endswith("APIRouter"):
            prefix = ""
            for kw in node.value.keywords:
                if kw.arg == "prefix":
                    prefix = literal_string(kw.value) or ""
            for target in node.targets:
                if isinstance(target, ast.Name):
                    prefixes[target.id] = prefix
    return prefixes


def _include_prefixes(tree: ast.AST) -> dict[str, str]:
    includes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _call_name(node.func).endswith("include_router"):
            continue
        router_name = None
        if node.args:
            router_name = _call_name(node.args[0])
        prefix = ""
        for kw in node.keywords:
            if kw.arg == "prefix":
                prefix = literal_string(kw.value) or ""
        if router_name:
            includes[router_name.split(".")[-1]] = prefix
    return includes


def _route_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef, router_prefixes: dict[str, str], include_prefixes: dict[str, str]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        name = _call_name(dec.func)
        method = name.split(".")[-1].lower()
        owner = name.split(".")[0] if "." in name else ""
        if method not in HTTP_METHODS:
            continue
        path = literal_string(dec.args[0]) if dec.args else None
        if not path:
            continue
        prefix = (include_prefixes.get(owner, "") or "") + (router_prefixes.get(owner, "") or "")
        routes.append(
            {
                "method": method.upper(),
                "path": _join_paths(prefix, path),
                "raw_path": path,
                "decorator": name,
                "kwargs": {kw.arg: node_to_source(kw.value) for kw in dec.keywords if kw.arg},
            }
        )
    return routes


def _endpoint_artifact(snapshot: RepoSnapshot, source: SourceFile, module_name: str, node: ast.FunctionDef | ast.AsyncFunctionDef, route: dict[str, Any]) -> ExtractedArtifact:
    method = route["method"]
    path = route["path"]
    locator = f"{method} {path}"
    params = _params(node)
    kwargs = route.get("kwargs", {})
    aid = stable_artifact_id(snapshot.repo_id, "endpoint", locator)
    return ExtractedArtifact(
        artifact_id=aid,
        category="endpoint",
        name=locator,
        canonical_locator=locator,
        source_file=source.path,
        source_line_start=getattr(node, "lineno", None),
        source_line_end=getattr(node, "end_lineno", None),
        payload={
            "method": method,
            "path": path,
            "handler": f"{module_name}.{node.name}",
            "params": params,
            "response_model": kwargs.get("response_model"),
            "status_code": kwargs.get("status_code"),
            "auth_dependencies": _auth_dependencies(node),
            "source_hash": source.source_hash,
        },
    )


def _function_artifact(snapshot: RepoSnapshot, source: SourceFile, module_name: str, node: ast.FunctionDef | ast.AsyncFunctionDef, owner: str | None = None) -> ExtractedArtifact:
    qn = f"{module_name}.{owner + '.' if owner else ''}{node.name}"
    decorators = [node_to_source(d) for d in node.decorator_list]
    aid = stable_artifact_id(snapshot.repo_id, "function", qn)
    return ExtractedArtifact(
        artifact_id=aid,
        category="function",
        name=qn,
        canonical_locator=qn,
        source_file=source.path,
        source_line_start=getattr(node, "lineno", None),
        source_line_end=getattr(node, "end_lineno", None),
        payload={
            "simple_name": node.name,
            "owner": owner,
            "signature": _signature(node),
            "params": _params(node),
            "return_type": node_to_source(node.returns),
            "decorators": [d for d in decorators if d],
            "docstring": ast.get_docstring(node),
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "callees": sorted(_callees(node)),
            "source_hash": source.source_hash,
        },
    )


def _model_artifact(snapshot: RepoSnapshot, source: SourceFile, module_name: str, node: ast.ClassDef) -> ExtractedArtifact | None:
    bases = [node_to_source(b) or "" for b in node.bases]
    decorators = [node_to_source(d) or "" for d in node.decorator_list]
    is_dataclass = any("dataclass" in d for d in decorators)
    is_pydantic = any("BaseModel" in b or "BaseSettings" in b for b in bases)
    is_sqlalchemy = any("Declarative" in b or b == "Base" for b in bases) or any(_contains_name(item, "mapped_column") for item in node.body)
    if not (is_dataclass or is_pydantic or is_sqlalchemy):
        return None
    qn = f"{module_name}.{node.name}"
    fields = []
    table_name = None
    validators = []
    relationships = []
    for item in node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id == "__tablename__":
                    table_name = literal_string(item.value)
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            default = node_to_source(item.value)
            call_name = _call_name(item.value.func) if isinstance(item.value, ast.Call) else ""
            fields.append(
                {
                    "name": item.target.id,
                    "type": node_to_source(item.annotation),
                    "default": default,
                    "nullable": "nullable=True" in (default or "") or "None" in (node_to_source(item.annotation) or ""),
                    "constraints": _keyword_payload(item.value) if isinstance(item.value, ast.Call) else {},
                }
            )
            if call_name.endswith("relationship"):
                relationships.append(item.target.id)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decs = " ".join(node_to_source(d) or "" for d in item.decorator_list)
            if "validator" in decs or "field_validator" in decs or "model_validator" in decs:
                validators.append(item.name)
    kind = "dataclass" if is_dataclass else "sqlalchemy" if is_sqlalchemy else "pydantic"
    aid = stable_artifact_id(snapshot.repo_id, "data_model", qn)
    return ExtractedArtifact(
        artifact_id=aid,
        category="data_model",
        name=qn,
        canonical_locator=qn,
        source_file=source.path,
        source_line_start=getattr(node, "lineno", None),
        source_line_end=getattr(node, "end_lineno", None),
        payload={
            "kind": kind,
            "base_classes": bases,
            "table_name": table_name,
            "fields": fields,
            "relationships": relationships,
            "validators": validators,
            "source_hash": source.source_hash,
        },
    )


def _extract_config(snapshot: RepoSnapshot, source: SourceFile) -> list[ExtractedArtifact]:
    name = source.path
    kind = _config_kind(source)
    payload: dict[str, Any] = {"kind": kind, "path": source.path, "source_hash": source.source_hash, "parse_errors": source.parse_errors}
    try:
        if source.path.endswith("package.json"):
            data = json.loads(source.text or "{}")
            payload.update({"scripts": data.get("scripts", {}), "dependencies": data.get("dependencies", {}), "dev_dependencies": data.get("devDependencies", {})})
        elif source.path.endswith("pyproject.toml"):
            data = tomllib.loads(source.text or "")
            payload.update({"project": data.get("project", {}), "tool": data.get("tool", {})})
        elif source.language == "yaml" and yaml is not None:
            payload["keys"] = list((yaml.safe_load(source.text or "") or {}).keys())
        elif source.language == "env":
            payload["vars"] = sorted({line.split("=", 1)[0].strip() for line in source.text.splitlines() if "=" in line and not line.lstrip().startswith("#")})
    except Exception as exc:
        payload["parse_errors"] = [*source.parse_errors, str(exc)]
    locator = f"{kind}:{source.path}"
    return [
        ExtractedArtifact(
            artifact_id=stable_artifact_id(snapshot.repo_id, "config", locator),
            category="config",
            name=name,
            canonical_locator=locator,
            source_file=source.path,
            source_line_start=1,
            source_line_end=max(1, source.loc),
            payload=payload,
        )
    ]


def _human_doc_artifact(snapshot: RepoSnapshot, source: SourceFile) -> ExtractedArtifact:
    locator = f"human_doc:{source.path}"
    return ExtractedArtifact(
        artifact_id=stable_artifact_id(snapshot.repo_id, "human_doc", locator),
        category="human_doc",
        name=source.path,
        canonical_locator=locator,
        source_file=source.path,
        source_line_start=1,
        source_line_end=max(1, source.loc),
        payload={"headings": source.top_level_symbols, "source_hash": source.source_hash},
    )


def _env_artifact(snapshot: RepoSnapshot, source: SourceFile, var: str, line: int | None) -> ExtractedArtifact:
    return ExtractedArtifact(
        artifact_id=stable_artifact_id(snapshot.repo_id, "env_var", var),
        category="env_var",
        name=var,
        canonical_locator=var,
        source_file=source.path,
        source_line_start=line,
        source_line_end=line,
        payload={"var_name": var, "secret_like": bool(re.search(r"(TOKEN|SECRET|KEY|PASSWORD)", var)), "source_hash": source.source_hash},
    )


def _params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + list(node.args.defaults)
    for arg, default in zip(node.args.args, defaults, strict=False):
        if arg.arg == "self":
            continue
        values.append({"name": arg.arg, "type": node_to_source(arg.annotation), "default": node_to_source(default), "kind": _param_kind(default)})
    return values


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = ", ".join(
        f"{p['name']}: {p['type']}" if p.get("type") else p["name"]
        for p in _params(node)
    )
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    ret = f" -> {node_to_source(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({args}){ret}"


def _param_kind(default: ast.AST | None) -> str:
    text = node_to_source(default) or ""
    if "Path(" in text:
        return "path"
    if "Query(" in text:
        return "query"
    if "Body(" in text:
        return "body"
    if "Depends(" in text or "Security(" in text:
        return "dependency"
    return "parameter"


def _auth_dependencies(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    deps: list[str] = []
    for param in _params(node):
        default = param.get("default") or ""
        if "Depends(" in default or "Security(" in default:
            deps.extend(re.findall(r"(?:Depends|Security)\(([\w\.]+)", default))
    return deps


def _callees(node: ast.AST) -> set[str]:
    calls: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _call_name(child.func)
            if name:
                calls.add(name)
    return calls


def _env_reads(node: ast.AST) -> list[tuple[str, int | None]]:
    values: list[tuple[str, int | None]] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = _call_name(child.func)
        if name in {"os.getenv", "os.environ.get", "environ.get"} and child.args:
            var = literal_string(child.args[0])
            if var:
                values.append((var, getattr(child, "lineno", None)))
    return values


def _module_env_reads(tree: ast.AST) -> list[tuple[str, int | None]]:
    return _env_reads(tree)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _join_paths(prefix: str, path: str) -> str:
    parts = [p.strip("/") for p in [prefix, path] if p and p != "/"]
    return "/" + "/".join(parts) if parts else "/"


def _contains_name(node: ast.AST, name: str) -> bool:
    return any(isinstance(child, ast.Name) and child.id == name or isinstance(child, ast.Attribute) and child.attr == name for child in ast.walk(node))


def _keyword_payload(call: ast.Call) -> dict[str, str | None]:
    return {kw.arg: node_to_source(kw.value) for kw in call.keywords if kw.arg}


def _is_config_source(source: SourceFile) -> bool:
    return (
        source.path.endswith("package.json")
        or source.path.endswith("pyproject.toml")
        or source.language in {"yaml", "env", "dockerfile"}
        or Path(source.path).name in {"Dockerfile", "docker-compose.yml", "compose.yml"}
    )


def _config_kind(source: SourceFile) -> str:
    name = Path(source.path).name.lower()
    if name == "package.json":
        return "package"
    if name == "pyproject.toml":
        return "python_project"
    if "docker" in name or "compose" in name:
        return "container"
    if ".github/workflows/" in source.path:
        return "github_actions"
    if source.language == "env":
        return "env_file"
    return source.language


def _is_human_doc(path: str) -> bool:
    return path.lower().endswith(".md") and not path.startswith(".aura/docs/")


def _import_edges(snapshot: RepoSnapshot, artifacts: list[ExtractedArtifact], module_by_path: dict[str, str]) -> list[ExtractedEdge]:
    module_by_name = {a.name: a.artifact_id for a in artifacts if a.category == "module"}
    edges: list[ExtractedEdge] = []
    for artifact in artifacts:
        if artifact.category != "module":
            continue
        for imp in artifact.payload.get("imports", []):
            cleaned = imp.lstrip(".")
            target = module_by_name.get(cleaned)
            if not target:
                target = next((mid for name, mid in module_by_name.items() if name.endswith(f".{cleaned}") or name == cleaned), None)
            if target:
                edges.append(ExtractedEdge(artifact.artifact_id, target, "imports"))
    return edges


def _resolved_call_edges(artifacts: list[ExtractedArtifact], function_by_simple_name: dict[str, list[str]]) -> list[ExtractedEdge]:
    edges: list[ExtractedEdge] = []
    for artifact in artifacts:
        if artifact.category != "function":
            continue
        for callee in artifact.payload.get("callees", []):
            simple = callee.split(".")[-1]
            matches = function_by_simple_name.get(simple, [])
            if len(matches) == 1 and matches[0] != artifact.artifact_id:
                edges.append(ExtractedEdge(artifact.artifact_id, matches[0], "calls"))
    return edges


def _dedupe_artifacts(artifacts: list[ExtractedArtifact]) -> list[ExtractedArtifact]:
    by_id: dict[str, ExtractedArtifact] = {}
    for artifact in artifacts:
        if artifact.artifact_id not in by_id:
            by_id[artifact.artifact_id] = artifact
        else:
            existing = by_id[artifact.artifact_id]
            files = set(existing.payload.get("source_files", []))
            if artifact.source_file:
                files.add(artifact.source_file)
            if existing.source_file:
                files.add(existing.source_file)
            existing.payload["source_files"] = sorted(files)
    return list(by_id.values())


def _dedupe_edges(edges: list[ExtractedEdge]) -> list[ExtractedEdge]:
    seen: set[tuple[str, str, str]] = set()
    out: list[ExtractedEdge] = []
    for edge in edges:
        key = (edge.src_artifact_id, edge.dst_artifact_id, edge.kind)
        if (edge.kind in EDGE_KINDS or edge.kind == "part_of_flow") and key not in seen:
            seen.add(key)
            out.append(edge)
    return out


def _summary(snapshot: RepoSnapshot, artifacts: list[ExtractedArtifact], edges: list[ExtractedEdge]) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    for artifact in artifacts:
        counts[artifact.category] += 1
    languages: dict[str, int] = defaultdict(int)
    for source in snapshot.files:
        languages[source.language] += 1
    return {
        "total_files": len(snapshot.files),
        "total_loc": snapshot.total_loc,
        "languages": dict(languages),
        "frameworks": snapshot.frameworks,
        "artifact_counts": dict(counts),
        "edge_count": len(edges),
        "parse_errors": [{"path": f.path, "errors": f.parse_errors} for f in snapshot.files if f.parse_errors],
    }
