"""Project-level aggregations over the extracted artifact graph.

Pure deterministic functions consumed by the project-doc planner and writers.
No LLM, no IO. Input is `(snapshot, artifacts, edges, summary)` from the
extract stage; output is a `ProjectAggregations` bundle.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .types import ExtractedArtifact, ExtractedEdge, RepoSnapshot, SourceFile


# ---------------------------------------------------------------------------
# Aggregation dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class EndpointEntry:
    method: str
    path: str
    handler_qn: str | None
    handler_file: str | None
    handler_line: int | None
    params: list[dict[str, Any]]
    response_model: str | None
    status_code: str | None
    auth_dependencies: list[str]
    source_file: str | None
    line_range: tuple[int | None, int | None]


@dataclass(slots=True)
class EndpointGroup:
    prefix: str
    endpoints: list[EndpointEntry]


@dataclass(slots=True)
class ModuleResponsibility:
    package_path: str
    cluster_name: str | None
    modules: list[str]
    languages: list[str]
    file_count: int
    loc: int
    top_callees: list[str]
    exports: list[str]
    fan_in: int
    fan_out: int


@dataclass(slots=True)
class DataModel:
    artifact_id: str
    name: str
    kind: str
    fields: list[dict[str, Any]]
    table_name: str | None
    relationships: list[str]
    base_classes: list[str]
    source_file: str | None
    line_range: tuple[int | None, int | None]


@dataclass(slots=True)
class DataModelGraph:
    models: list[DataModel]
    references: list[dict[str, str]]


@dataclass(slots=True)
class EnvVar:
    var: str
    sites: list[tuple[str, int | None]]
    secret_like: bool
    defining_config_files: list[str]


@dataclass(slots=True)
class ConfigEntry:
    path: str
    kind: str
    summary_keys: list[str]
    scripts: dict[str, str] | None
    dependencies: dict[str, str] | None
    parse_errors: list[str]


@dataclass(slots=True)
class IntegrationEvidence:
    file: str
    line: int | None
    signal: str


@dataclass(slots=True)
class ExternalIntegration:
    name: str
    category: str
    evidence: list[IntegrationEvidence]


@dataclass(slots=True)
class AuthDependencyUsage:
    name: str
    endpoints: list[str]


@dataclass(slots=True)
class AuthSecurityView:
    auth_dependencies: list[AuthDependencyUsage]
    protected_endpoints: list[dict[str, Any]]
    secret_env_vars: list[str]
    oauth_signals: list[str]


@dataclass(slots=True)
class BackgroundJob:
    name: str
    type: str
    file: str
    line: int | None
    schedule_or_trigger: str | None


@dataclass(slots=True)
class WorkflowTrace:
    name: str
    entry_id: str
    entry_method: str
    entry_path: str
    path: list[str]
    reads_env: list[str]
    writes_models: list[str]
    calls_external: list[str]


@dataclass(slots=True)
class FrontendPage:
    path: str
    component: str | None
    file: str
    line: int | None


@dataclass(slots=True)
class FrontendComponent:
    name: str
    file: str
    line: int | None
    exports: list[str]


@dataclass(slots=True)
class FrontendStateStore:
    name: str
    kind: str
    file: str
    line: int | None


@dataclass(slots=True)
class FrontendView:
    pages: list[FrontendPage]
    components: list[FrontendComponent]
    state_stores: list[FrontendStateStore]


@dataclass(slots=True)
class CliCommand:
    command: str
    file: str
    line: int | None
    description: str | None


@dataclass(slots=True)
class IacResource:
    resource: str
    file: str
    line: int | None
    kind: str


@dataclass(slots=True)
class MlView:
    model_files: list[dict[str, str]]
    pipeline_dags: list[dict[str, Any]]


@dataclass(slots=True)
class ProjectAggregations:
    endpoint_catalog: list[EndpointGroup] = field(default_factory=list)
    module_responsibility_map: list[ModuleResponsibility] = field(default_factory=list)
    data_model_graph: DataModelGraph = field(default_factory=lambda: DataModelGraph([], []))
    env_var_inventory: list[EnvVar] = field(default_factory=list)
    config_inventory: list[ConfigEntry] = field(default_factory=list)
    external_integrations: list[ExternalIntegration] = field(default_factory=list)
    auth_security_view: AuthSecurityView = field(
        default_factory=lambda: AuthSecurityView([], [], [], [])
    )
    background_jobs_view: list[BackgroundJob] = field(default_factory=list)
    workflow_traces: list[WorkflowTrace] = field(default_factory=list)
    frontend_view: FrontendView = field(default_factory=lambda: FrontendView([], [], []))
    cli_view: list[CliCommand] = field(default_factory=list)
    iac_view: list[IacResource] = field(default_factory=list)
    ml_view: MlView = field(default_factory=lambda: MlView([], []))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_project_aggregations(
    snapshot: RepoSnapshot,
    artifacts: list[ExtractedArtifact],
    edges: list[ExtractedEdge],
    summary: dict[str, Any],
) -> ProjectAggregations:
    by_id = {a.artifact_id: a for a in artifacts}
    files_by_path = {f.path: f for f in snapshot.files}

    endpoint_catalog = _endpoint_catalog(artifacts, edges, by_id)
    module_map = _module_responsibility_map(snapshot, artifacts, edges)
    model_graph = _data_model_graph(artifacts, edges, by_id)
    env_inventory = _env_var_inventory(artifacts, edges, by_id)
    config_inventory = _config_inventory(artifacts)
    integrations = _external_integrations(snapshot, artifacts, files_by_path)
    auth_view = _auth_security_view(artifacts, edges, env_inventory, snapshot.frameworks)
    bg_jobs = _background_jobs_view(artifacts, files_by_path)
    workflows = _workflow_traces(artifacts, edges, by_id, integrations)
    frontend = _frontend_view(snapshot, artifacts, files_by_path)
    cli = _cli_view(artifacts, files_by_path)
    iac = _iac_view(snapshot)
    ml = _ml_view(snapshot, artifacts)

    return ProjectAggregations(
        endpoint_catalog=endpoint_catalog,
        module_responsibility_map=module_map,
        data_model_graph=model_graph,
        env_var_inventory=env_inventory,
        config_inventory=config_inventory,
        external_integrations=integrations,
        auth_security_view=auth_view,
        background_jobs_view=bg_jobs,
        workflow_traces=workflows,
        frontend_view=frontend,
        cli_view=cli,
        iac_view=iac,
        ml_view=ml,
    )


# ---------------------------------------------------------------------------
# Endpoint catalog
# ---------------------------------------------------------------------------


def _endpoint_catalog(
    artifacts: list[ExtractedArtifact],
    edges: list[ExtractedEdge],
    by_id: dict[str, ExtractedArtifact],
) -> list[EndpointGroup]:
    handler_by_endpoint: dict[str, str] = {}
    for edge in edges:
        if edge.kind == "handles_endpoint":
            handler_by_endpoint[edge.src_artifact_id] = edge.dst_artifact_id

    grouped: dict[str, list[EndpointEntry]] = defaultdict(list)
    for artifact in artifacts:
        if artifact.category != "endpoint":
            continue
        payload = artifact.payload
        handler_id = handler_by_endpoint.get(artifact.artifact_id)
        handler = by_id.get(handler_id) if handler_id else None
        path = payload.get("path", "/") or "/"
        prefix = _path_prefix(path)
        grouped[prefix].append(
            EndpointEntry(
                method=payload.get("method", "GET"),
                path=path,
                handler_qn=payload.get("handler"),
                handler_file=handler.source_file if handler else artifact.source_file,
                handler_line=handler.source_line_start if handler else artifact.source_line_start,
                params=list(payload.get("params") or []),
                response_model=payload.get("response_model"),
                status_code=payload.get("status_code"),
                auth_dependencies=list(payload.get("auth_dependencies") or []),
                source_file=artifact.source_file,
                line_range=(artifact.source_line_start, artifact.source_line_end),
            )
        )

    groups = [
        EndpointGroup(prefix=prefix, endpoints=sorted(eps, key=lambda e: (e.path, e.method)))
        for prefix, eps in grouped.items()
    ]
    return sorted(groups, key=lambda g: g.prefix)


def _path_prefix(path: str) -> str:
    parts = [p for p in path.split("/") if p and not p.startswith("{")]
    return f"/{parts[0]}" if parts else "/"


# ---------------------------------------------------------------------------
# Module responsibility map
# ---------------------------------------------------------------------------


def _module_responsibility_map(
    snapshot: RepoSnapshot,
    artifacts: list[ExtractedArtifact],
    edges: list[ExtractedEdge],
) -> list[ModuleResponsibility]:
    modules = [a for a in artifacts if a.category == "module"]
    if not modules:
        return []

    flow_by_module: dict[str, str] = {}
    for artifact in artifacts:
        if artifact.category == "flow":
            for module_name in artifact.payload.get("modules", []):
                flow_by_module[module_name] = artifact.name

    fan_in: Counter[str] = Counter()
    fan_out: Counter[str] = Counter()
    for edge in edges:
        if edge.kind == "imports":
            fan_in[edge.dst_artifact_id] += 1
            fan_out[edge.src_artifact_id] += 1

    callees_by_package: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for artifact in artifacts:
        if artifact.category == "function":
            pkg = _package_from_qn(artifact.name)
            for callee in artifact.payload.get("callees", []):
                callees_by_package[pkg][callee.split(".")[-1]] += 1

    grouped: defaultdict[str, list[ExtractedArtifact]] = defaultdict(list)
    for module in modules:
        pkg = _package_from_qn(module.name)
        grouped[pkg].append(module)

    result: list[ModuleResponsibility] = []
    for pkg, mods in sorted(grouped.items()):
        languages = sorted({m.payload.get("language", "unknown") for m in mods})
        loc = sum(int(m.payload.get("loc", 0) or 0) for m in mods)
        exports: list[str] = []
        for m in mods:
            exports.extend(m.payload.get("exports", []) or [])
        cluster = next((flow_by_module.get(m.name) for m in mods if flow_by_module.get(m.name)), None)
        top_callees = [name for name, _ in callees_by_package.get(pkg, Counter()).most_common(8)]
        result.append(
            ModuleResponsibility(
                package_path=pkg,
                cluster_name=cluster,
                modules=sorted(m.name for m in mods),
                languages=languages,
                file_count=len(mods),
                loc=loc,
                top_callees=top_callees,
                exports=sorted(set(exports))[:40],
                fan_in=sum(fan_in[m.artifact_id] for m in mods),
                fan_out=sum(fan_out[m.artifact_id] for m in mods),
            )
        )
    return result


def _package_from_qn(qn: str) -> str:
    parts = qn.split(".")
    if len(parts) <= 2:
        return parts[0] if parts else qn
    return ".".join(parts[:2])


# ---------------------------------------------------------------------------
# Data model graph
# ---------------------------------------------------------------------------


def _data_model_graph(
    artifacts: list[ExtractedArtifact],
    edges: list[ExtractedEdge],
    by_id: dict[str, ExtractedArtifact],
) -> DataModelGraph:
    models: list[DataModel] = []
    model_ids: set[str] = set()
    for artifact in artifacts:
        if artifact.category != "data_model":
            continue
        payload = artifact.payload
        models.append(
            DataModel(
                artifact_id=artifact.artifact_id,
                name=artifact.name,
                kind=payload.get("kind", "unknown"),
                fields=list(payload.get("fields") or []),
                table_name=payload.get("table_name"),
                relationships=list(payload.get("relationships") or []),
                base_classes=list(payload.get("base_classes") or []),
                source_file=artifact.source_file,
                line_range=(artifact.source_line_start, artifact.source_line_end),
            )
        )
        model_ids.add(artifact.artifact_id)

    references: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        if edge.kind != "uses_model":
            continue
        if edge.src_artifact_id not in model_ids or edge.dst_artifact_id not in model_ids:
            continue
        key = (edge.src_artifact_id, edge.dst_artifact_id, edge.kind)
        if key in seen:
            continue
        seen.add(key)
        src = by_id.get(edge.src_artifact_id)
        dst = by_id.get(edge.dst_artifact_id)
        if src and dst:
            references.append({"src": src.name, "dst": dst.name, "kind": "uses_model"})

    return DataModelGraph(models=sorted(models, key=lambda m: m.name), references=references)


# ---------------------------------------------------------------------------
# Env var inventory
# ---------------------------------------------------------------------------


def _env_var_inventory(
    artifacts: list[ExtractedArtifact],
    edges: list[ExtractedEdge],
    by_id: dict[str, ExtractedArtifact],
) -> list[EnvVar]:
    env_artifacts = [a for a in artifacts if a.category == "env_var"]
    if not env_artifacts:
        return []

    sites_by_var: defaultdict[str, list[tuple[str, int | None]]] = defaultdict(list)
    for env in env_artifacts:
        if env.source_file:
            sites_by_var[env.name].append((env.source_file, env.source_line_start))

    for edge in edges:
        if edge.kind != "reads_env":
            continue
        env = by_id.get(edge.dst_artifact_id)
        reader = by_id.get(edge.src_artifact_id)
        if not env or env.category != "env_var" or not reader:
            continue
        if reader.source_file:
            sites_by_var[env.name].append((reader.source_file, reader.source_line_start))

    config_vars: defaultdict[str, list[str]] = defaultdict(list)
    for artifact in artifacts:
        if artifact.category != "config":
            continue
        for var in artifact.payload.get("vars", []) or []:
            config_vars[var].append(artifact.source_file or artifact.name)

    by_name: dict[str, EnvVar] = {}
    for env in env_artifacts:
        if env.name in by_name:
            continue
        sites = sorted(set(sites_by_var.get(env.name, [])))
        by_name[env.name] = EnvVar(
            var=env.name,
            sites=sites,
            secret_like=bool(env.payload.get("secret_like")),
            defining_config_files=sorted(set(config_vars.get(env.name, []))),
        )
    return sorted(by_name.values(), key=lambda e: e.var)


# ---------------------------------------------------------------------------
# Config inventory
# ---------------------------------------------------------------------------


def _config_inventory(artifacts: list[ExtractedArtifact]) -> list[ConfigEntry]:
    entries: list[ConfigEntry] = []
    for artifact in artifacts:
        if artifact.category != "config":
            continue
        payload = artifact.payload
        kind = payload.get("kind", "unknown")
        scripts = payload.get("scripts")
        dependencies = payload.get("dependencies")
        keys: list[str] = []
        if "vars" in payload:
            keys = list(payload["vars"])
        elif "keys" in payload:
            keys = list(payload["keys"])
        elif "project" in payload:
            keys = list((payload["project"] or {}).keys())
        elif scripts:
            keys = list(scripts.keys())
        keys = [str(k) for k in keys if k is not None]
        entries.append(
            ConfigEntry(
                path=payload.get("path", artifact.source_file or artifact.name),
                kind=kind,
                summary_keys=sorted(keys)[:30],
                scripts=dict(scripts) if isinstance(scripts, dict) else None,
                dependencies=dict(dependencies) if isinstance(dependencies, dict) else None,
                parse_errors=list(payload.get("parse_errors") or []),
            )
        )
    return sorted(entries, key=lambda c: c.path)


# ---------------------------------------------------------------------------
# External integrations
# ---------------------------------------------------------------------------


_INTEGRATION_REGISTRY: list[tuple[str, str, str]] = [
    # (match_prefix, name, category)
    ("httpx", "httpx", "http_client"),
    ("requests", "requests", "http_client"),
    ("aiohttp", "aiohttp", "http_client"),
    ("urllib3", "urllib3", "http_client"),
    ("axios", "axios", "http_client"),
    ("sqlalchemy", "sqlalchemy", "db_driver"),
    ("psycopg", "psycopg", "db_driver"),
    ("asyncpg", "asyncpg", "db_driver"),
    ("pymongo", "pymongo", "db_driver"),
    ("aiomysql", "aiomysql", "db_driver"),
    ("aiosqlite", "aiosqlite", "db_driver"),
    ("redis", "redis", "cache"),
    ("aiocache", "aiocache", "cache"),
    ("memcache", "memcache", "cache"),
    ("celery", "celery", "queue"),
    ("rq", "rq", "queue"),
    ("dramatiq", "dramatiq", "queue"),
    ("arq", "arq", "queue"),
    ("kombu", "kombu", "queue"),
    ("apscheduler", "apscheduler", "queue"),
    ("boto3", "boto3", "cloud_sdk"),
    ("botocore", "botocore", "cloud_sdk"),
    ("google.cloud", "google-cloud", "cloud_sdk"),
    ("google.auth", "google-auth", "cloud_sdk"),
    ("azure", "azure", "cloud_sdk"),
    ("openai", "openai", "ai_provider"),
    ("anthropic", "anthropic", "ai_provider"),
    ("cohere", "cohere", "ai_provider"),
    ("langchain", "langchain", "ai_provider"),
    ("transformers", "transformers", "ai_provider"),
    ("sentry_sdk", "sentry_sdk", "observability"),
    ("opentelemetry", "opentelemetry", "observability"),
    ("prometheus_client", "prometheus_client", "observability"),
    ("structlog", "structlog", "observability"),
    ("authlib", "authlib", "auth_provider"),
    ("oauthlib", "oauthlib", "auth_provider"),
    ("jwt", "pyjwt", "auth_provider"),
    ("passlib", "passlib", "auth_provider"),
    ("bcrypt", "bcrypt", "auth_provider"),
    ("github", "PyGithub", "external_api"),
    ("react", "react", "ui_framework"),
    ("react-router", "react-router", "ui_framework"),
    ("react-flow", "react-flow", "ui_framework"),
    ("zustand", "zustand", "state"),
    ("redux", "redux", "state"),
    ("recoil", "recoil", "state"),
]


def _external_integrations(
    snapshot: RepoSnapshot,
    artifacts: list[ExtractedArtifact],
    files_by_path: dict[str, SourceFile],
) -> list[ExternalIntegration]:
    evidence_by_name: defaultdict[str, list[IntegrationEvidence]] = defaultdict(list)
    category_by_name: dict[str, str] = {}

    for artifact in artifacts:
        if artifact.category != "module":
            continue
        imports = artifact.payload.get("imports") or []
        for imp in imports:
            base = imp.lstrip(".").split(".")[0]
            full = imp.lstrip(".")
            for prefix, name, category in _INTEGRATION_REGISTRY:
                if full == prefix or full.startswith(prefix + ".") or base == prefix:
                    evidence_by_name[name].append(
                        IntegrationEvidence(
                            file=artifact.source_file or "",
                            line=None,
                            signal=f"import {imp}",
                        )
                    )
                    category_by_name[name] = category
                    break

    for cfg in artifacts:
        if cfg.category != "config":
            continue
        deps = cfg.payload.get("dependencies") or {}
        dev_deps = cfg.payload.get("dev_dependencies") or {}
        for dep_name in list(deps.keys()) + list(dev_deps.keys()):
            for prefix, name, category in _INTEGRATION_REGISTRY:
                if dep_name == prefix or dep_name.startswith(prefix + "/") or dep_name.startswith("@" + prefix):
                    evidence_by_name[name].append(
                        IntegrationEvidence(
                            file=cfg.source_file or cfg.name,
                            line=None,
                            signal=f"dependency {dep_name}",
                        )
                    )
                    category_by_name[name] = category
                    break

    integrations: list[ExternalIntegration] = []
    for name, evidence in evidence_by_name.items():
        # Cap evidence per integration to keep prompts small
        capped = evidence[:6]
        integrations.append(
            ExternalIntegration(
                name=name,
                category=category_by_name.get(name, "unknown"),
                evidence=capped,
            )
        )
    return sorted(integrations, key=lambda i: (i.category, i.name))


# ---------------------------------------------------------------------------
# Auth & security view
# ---------------------------------------------------------------------------


_OAUTH_IMPORT_PATTERNS = ("authlib", "oauthlib", "google.oauth2", "google_auth_oauthlib", "msal")


def _auth_security_view(
    artifacts: list[ExtractedArtifact],
    edges: list[ExtractedEdge],
    env_vars: list[EnvVar],
    frameworks: list[str],
) -> AuthSecurityView:
    protected: list[dict[str, Any]] = []
    deps_usage: defaultdict[str, list[str]] = defaultdict(list)
    for artifact in artifacts:
        if artifact.category != "endpoint":
            continue
        deps = artifact.payload.get("auth_dependencies") or []
        if not deps:
            continue
        protected.append(
            {
                "method": artifact.payload.get("method"),
                "path": artifact.payload.get("path"),
                "handler": artifact.payload.get("handler"),
                "auth_dependencies": list(deps),
                "source_file": artifact.source_file,
            }
        )
        for dep in deps:
            deps_usage[dep].append(f"{artifact.payload.get('method')} {artifact.payload.get('path')}")

    auth_deps = [
        AuthDependencyUsage(name=name, endpoints=sorted(set(eps)))
        for name, eps in sorted(deps_usage.items())
    ]

    secret_vars = sorted({v.var for v in env_vars if v.secret_like})

    oauth_signals: list[str] = []
    for fw in frameworks:
        if fw.lower() in {"oauth", "oauthlib", "authlib"}:
            oauth_signals.append(f"framework:{fw}")
    for artifact in artifacts:
        if artifact.category != "module":
            continue
        for imp in artifact.payload.get("imports") or []:
            base = imp.lstrip(".")
            if any(base.startswith(pat) for pat in _OAUTH_IMPORT_PATTERNS):
                oauth_signals.append(f"{artifact.source_file}:import {base}")
                break
    if any("jwt" in v.lower() for v in secret_vars):
        oauth_signals.append("secret_var:JWT")

    return AuthSecurityView(
        auth_dependencies=auth_deps,
        protected_endpoints=protected,
        secret_env_vars=secret_vars,
        oauth_signals=sorted(set(oauth_signals))[:20],
    )


# ---------------------------------------------------------------------------
# Background jobs
# ---------------------------------------------------------------------------


_JOB_DECORATOR_PATTERNS = [
    (re.compile(r"@?celery[\w\.]*\.task"), "celery"),
    (re.compile(r"@?app\.task\b"), "celery"),
    (re.compile(r"@?dramatiq\.actor"), "dramatiq"),
    (re.compile(r"@?dramatiq\.message"), "dramatiq"),
    (re.compile(r"@?rq\.job"), "rq"),
    (re.compile(r"@?arq\.cron"), "arq"),
    (re.compile(r"scheduler\.scheduled_job"), "apscheduler"),
    (re.compile(r"scheduler\.add_job"), "apscheduler"),
    (re.compile(r"asyncio\.create_task"), "asyncio_task"),
    (re.compile(r"BackgroundTasks"), "fastapi_bg_tasks"),
]


def _background_jobs_view(
    artifacts: list[ExtractedArtifact],
    files_by_path: dict[str, SourceFile],
) -> list[BackgroundJob]:
    jobs: list[BackgroundJob] = []
    for artifact in artifacts:
        if artifact.category != "function":
            continue
        decorators = artifact.payload.get("decorators") or []
        deco_text = " ".join(decorators)
        callees = " ".join(artifact.payload.get("callees") or [])
        haystack = deco_text + " " + callees
        for pattern, kind in _JOB_DECORATOR_PATTERNS:
            if pattern.search(haystack):
                jobs.append(
                    BackgroundJob(
                        name=artifact.name,
                        type=kind,
                        file=artifact.source_file or "",
                        line=artifact.source_line_start,
                        schedule_or_trigger=_extract_schedule(decorators),
                    )
                )
                break

    # Module-level scans for cron-style YAML / GitHub Actions schedules
    for path, source in files_by_path.items():
        if not (path.endswith(".yml") or path.endswith(".yaml")):
            continue
        if "cron:" in source.text:
            for idx, line in enumerate(source.text.splitlines(), start=1):
                if "cron:" in line:
                    jobs.append(
                        BackgroundJob(
                            name=f"cron@{path}:{idx}",
                            type="cron",
                            file=path,
                            line=idx,
                            schedule_or_trigger=line.split("cron:", 1)[1].strip().strip("'\""),
                        )
                    )
                    break
    return jobs


def _extract_schedule(decorators: list[str]) -> str | None:
    for dec in decorators:
        m = re.search(r"(cron|every|seconds|minutes|hours|days)\s*=\s*['\"]?([^'\"\)]+)", dec)
        if m:
            return f"{m.group(1)}={m.group(2)}"
    return None


# ---------------------------------------------------------------------------
# Workflow traces (BFS from endpoints)
# ---------------------------------------------------------------------------


_WORKFLOW_MAX_DEPTH = 4
_WORKFLOW_MAX_FANOUT = 6


def _workflow_traces(
    artifacts: list[ExtractedArtifact],
    edges: list[ExtractedEdge],
    by_id: dict[str, ExtractedArtifact],
    integrations: list[ExternalIntegration],
) -> list[WorkflowTrace]:
    out_edges: defaultdict[str, list[ExtractedEdge]] = defaultdict(list)
    for edge in edges:
        out_edges[edge.src_artifact_id].append(edge)

    integration_names = {i.name.lower() for i in integrations}

    traces: list[WorkflowTrace] = []
    for artifact in artifacts:
        if artifact.category != "endpoint":
            continue
        path: list[str] = [artifact.artifact_id]
        reads_env: set[str] = set()
        writes_models: set[str] = set()
        calls_external: set[str] = set()

        visited: set[str] = {artifact.artifact_id}
        frontier: list[tuple[str, int]] = [(artifact.artifact_id, 0)]

        while frontier:
            node_id, depth = frontier.pop(0)
            if depth >= _WORKFLOW_MAX_DEPTH:
                continue
            children = out_edges.get(node_id, [])[:_WORKFLOW_MAX_FANOUT]
            for edge in children:
                target = by_id.get(edge.dst_artifact_id)
                if not target:
                    continue
                if edge.kind == "reads_env":
                    reads_env.add(target.name)
                elif edge.kind == "uses_model":
                    if target.category == "data_model":
                        writes_models.add(target.name)
                elif edge.kind in ("calls", "handles_endpoint"):
                    if target.artifact_id not in visited and target.category == "function":
                        visited.add(target.artifact_id)
                        path.append(target.artifact_id)
                        frontier.append((target.artifact_id, depth + 1))
                        # Approximate external calls via callees matching integration names
                        for callee in target.payload.get("callees") or []:
                            base = callee.split(".")[0].lower()
                            if base in integration_names:
                                calls_external.add(base)

        traces.append(
            WorkflowTrace(
                name=f"{artifact.payload.get('method')} {artifact.payload.get('path')}",
                entry_id=artifact.artifact_id,
                entry_method=artifact.payload.get("method", ""),
                entry_path=artifact.payload.get("path", ""),
                path=path,
                reads_env=sorted(reads_env),
                writes_models=sorted(writes_models),
                calls_external=sorted(calls_external),
            )
        )
    return traces


# ---------------------------------------------------------------------------
# Frontend view
# ---------------------------------------------------------------------------


_ROUTE_RE = re.compile(r"<Route\s+[^>]*?path=[\"']([^\"']+)[\"'][^>]*?(?:element|component)=\{<?(\w+)")
_ROUTE_PATH_ONLY_RE = re.compile(r"<Route\s+[^>]*?path=[\"']([^\"']+)[\"']")
_FRONTEND_EXTS = (".tsx", ".ts", ".jsx", ".js")


def _frontend_view(
    snapshot: RepoSnapshot,
    artifacts: list[ExtractedArtifact],
    files_by_path: dict[str, SourceFile],
) -> FrontendView:
    pages: list[FrontendPage] = []
    components: list[FrontendComponent] = []
    state_stores: list[FrontendStateStore] = []

    for path, source in files_by_path.items():
        if not path.endswith(_FRONTEND_EXTS):
            continue
        text = source.text or ""
        if "<Route" in text:
            for line_no, line in enumerate(text.splitlines(), start=1):
                m = _ROUTE_RE.search(line)
                if m:
                    pages.append(
                        FrontendPage(path=m.group(1), component=m.group(2), file=path, line=line_no)
                    )
                    continue
                m2 = _ROUTE_PATH_ONLY_RE.search(line)
                if m2:
                    pages.append(
                        FrontendPage(path=m2.group(1), component=None, file=path, line=line_no)
                    )

    for artifact in artifacts:
        if artifact.category != "module":
            continue
        if not artifact.source_file or not artifact.source_file.endswith(_FRONTEND_EXTS):
            continue
        exports = artifact.payload.get("exports") or []
        component_exports = [e for e in exports if e and e[0].isupper()]
        if not component_exports:
            continue
        components.append(
            FrontendComponent(
                name=Path(artifact.source_file).stem,
                file=artifact.source_file,
                line=artifact.source_line_start,
                exports=component_exports[:10],
            )
        )

    state_signals = {
        "zustand": "zustand",
        "redux": "redux",
        "@reduxjs/toolkit": "redux_toolkit",
        "recoil": "recoil",
        "jotai": "jotai",
        "mobx": "mobx",
    }
    for path, source in files_by_path.items():
        if not path.endswith(_FRONTEND_EXTS):
            continue
        text = source.text or ""
        for needle, kind in state_signals.items():
            if needle in text:
                state_stores.append(
                    FrontendStateStore(
                        name=needle,
                        kind=kind,
                        file=path,
                        line=None,
                    )
                )
                break
        if "createContext" in text and "Provider" in text:
            state_stores.append(
                FrontendStateStore(
                    name=Path(path).stem,
                    kind="react_context",
                    file=path,
                    line=None,
                )
            )

    # dedupe components/pages/stores by (name, file)
    pages = _dedupe_by(pages, lambda p: (p.path, p.file, p.line))
    components = _dedupe_by(components, lambda c: (c.name, c.file))
    state_stores = _dedupe_by(state_stores, lambda s: (s.name, s.file))

    return FrontendView(pages=pages, components=components, state_stores=state_stores)


def _dedupe_by(items: list[Any], key: Any) -> list[Any]:
    seen: set[Any] = set()
    out: list[Any] = []
    for item in items:
        k = key(item)
        if k in seen:
            continue
        seen.add(k)
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# CLI view
# ---------------------------------------------------------------------------


_CLI_DECO_PATTERNS = [
    re.compile(r"@\w+\.command\b"),
    re.compile(r"@click\.command"),
    re.compile(r"@typer\.\w+"),
    re.compile(r"@app\.command"),
]


def _cli_view(
    artifacts: list[ExtractedArtifact],
    files_by_path: dict[str, SourceFile],
) -> list[CliCommand]:
    commands: list[CliCommand] = []
    for artifact in artifacts:
        if artifact.category != "function":
            continue
        decorators = artifact.payload.get("decorators") or []
        deco_text = " ".join(decorators)
        if any(p.search(deco_text) for p in _CLI_DECO_PATTERNS):
            commands.append(
                CliCommand(
                    command=artifact.payload.get("simple_name") or artifact.name.split(".")[-1],
                    file=artifact.source_file or "",
                    line=artifact.source_line_start,
                    description=(artifact.payload.get("docstring") or "").splitlines()[0] if artifact.payload.get("docstring") else None,
                )
            )

    # argparse module-level usage
    for path, source in files_by_path.items():
        if source.language != "python":
            continue
        text = source.text or ""
        if "argparse.ArgumentParser" in text or "ArgumentParser(" in text:
            for line_no, line in enumerate(text.splitlines(), start=1):
                m = re.search(r"add_argument\(\s*['\"]([^'\"]+)['\"]", line)
                if m:
                    commands.append(
                        CliCommand(
                            command=m.group(1),
                            file=path,
                            line=line_no,
                            description=None,
                        )
                    )
    return commands


# ---------------------------------------------------------------------------
# IaC view
# ---------------------------------------------------------------------------


def _iac_view(snapshot: RepoSnapshot) -> list[IacResource]:
    resources: list[IacResource] = []
    for source in snapshot.files:
        path = source.path
        name = Path(path).name.lower()
        if path.endswith(".tf"):
            for line_no, line in enumerate((source.text or "").splitlines(), start=1):
                m = re.match(r'\s*(resource|module|data)\s+"([^"]+)"\s+"([^"]+)"', line)
                if m:
                    resources.append(
                        IacResource(
                            resource=f"{m.group(1)}.{m.group(2)}.{m.group(3)}",
                            file=path,
                            line=line_no,
                            kind="terraform",
                        )
                    )
        elif name in {"dockerfile"} or name.startswith("dockerfile"):
            resources.append(
                IacResource(resource=name, file=path, line=1, kind="docker")
            )
        elif name in {"docker-compose.yml", "compose.yml", "docker-compose.yaml"}:
            resources.append(
                IacResource(resource=name, file=path, line=1, kind="docker_compose")
            )
        elif (path.endswith(".yml") or path.endswith(".yaml")) and "kind:" in (source.text or ""):
            for line_no, line in enumerate(source.text.splitlines(), start=1):
                m = re.match(r"\s*kind:\s*(\w+)", line)
                if m:
                    resources.append(
                        IacResource(
                            resource=m.group(1),
                            file=path,
                            line=line_no,
                            kind="kubernetes",
                        )
                    )
                    break
    return resources


# ---------------------------------------------------------------------------
# ML view
# ---------------------------------------------------------------------------


_ML_FRAMEWORKS = ("torch", "tensorflow", "keras", "sklearn", "xgboost", "lightgbm", "transformers")


def _ml_view(snapshot: RepoSnapshot, artifacts: list[ExtractedArtifact]) -> MlView:
    model_files: list[dict[str, str]] = []
    for source in snapshot.files:
        if source.language != "python":
            continue
        for fw in _ML_FRAMEWORKS:
            if any(imp.startswith(fw) for imp in source.imports):
                model_files.append({"path": source.path, "framework": fw})
                break
    return MlView(model_files=model_files, pipeline_dags=[])
