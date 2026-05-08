"""Project-level documentation type registry.

Each `DocTypeSpec` declares: identity, output path, required aggregations,
applicability rule, and the per-doc-type body outline + task brief that the
generic writer feeds to the LLM. The registry is the source of truth for the
22 known doc types; the LLM may also propose `extra:<slug>` doc types at
plan time which are written into `.aura/docs/extra/<slug>.md`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from .aggregators import ProjectAggregations
from .types import RepoSnapshot


DiataxisType = Literal["explanation", "reference", "how-to", "tutorial"]


@dataclass(slots=True, frozen=True)
class DocTypeSpec:
    id: str
    title: str
    diataxis: DiataxisType
    output_path_template: str
    required_aggregations: tuple[str, ...]
    applicability_rule: Callable[[RepoSnapshot, dict[str, Any], ProjectAggregations], bool]
    task_brief: str
    body_outline: tuple[str, ...]
    always_on: bool = False
    extensible: bool = False


# ---------------------------------------------------------------------------
# Applicability helpers
# ---------------------------------------------------------------------------


def _always(_s, _summary, _aggs) -> bool:
    return True


def _has_endpoints(_s, _summary, aggs: ProjectAggregations) -> bool:
    return any(g.endpoints for g in aggs.endpoint_catalog)


def _has_models(_s, _summary, aggs: ProjectAggregations) -> bool:
    return bool(aggs.data_model_graph.models)


def _has_protected_or_secrets(_s, _summary, aggs: ProjectAggregations) -> bool:
    return bool(aggs.auth_security_view.protected_endpoints) or bool(aggs.auth_security_view.secret_env_vars)


def _has_jobs(_s, _summary, aggs: ProjectAggregations) -> bool:
    return bool(aggs.background_jobs_view)


def _has_integrations(_s, _summary, aggs: ProjectAggregations) -> bool:
    return bool(aggs.external_integrations)


def _has_modules(_s, _summary, aggs: ProjectAggregations) -> bool:
    return bool(aggs.module_responsibility_map)


def _has_workflows(_s, _summary, aggs: ProjectAggregations) -> bool:
    return bool(aggs.workflow_traces) or _has_modules(_s, _summary, aggs)


def _has_pages(_s, _summary, aggs: ProjectAggregations) -> bool:
    return bool(aggs.frontend_view.pages)


def _has_components(_s, _summary, aggs: ProjectAggregations) -> bool:
    return len(aggs.frontend_view.components) >= 5


def _has_state(_s, _summary, aggs: ProjectAggregations) -> bool:
    return bool(aggs.frontend_view.state_stores)


def _has_cli(_s, _summary, aggs: ProjectAggregations) -> bool:
    return bool(aggs.cli_view)


def _is_library(snapshot: RepoSnapshot, _summary, aggs: ProjectAggregations) -> bool:
    has_pyproject = any(f.path.endswith("pyproject.toml") for f in snapshot.files)
    has_endpoints = _has_endpoints(snapshot, _summary, aggs)
    has_top_exports = any(m.exports for m in aggs.module_responsibility_map)
    return has_pyproject and not has_endpoints and has_top_exports


def _has_iac(_s, _summary, aggs: ProjectAggregations) -> bool:
    return bool(aggs.iac_view)


def _has_ml(_s, _summary, aggs: ProjectAggregations) -> bool:
    return bool(aggs.ml_view.model_files)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def _spec(**kwargs) -> DocTypeSpec:
    return DocTypeSpec(**kwargs)


DOC_TYPE_REGISTRY: dict[str, DocTypeSpec] = {
    # ---- Always-on (9) ------------------------------------------------
    "overview": _spec(
        id="overview",
        title="Project Overview",
        diataxis="explanation",
        output_path_template=".aura/docs/overview.md",
        required_aggregations=("module_responsibility_map", "external_integrations", "config_inventory"),
        applicability_rule=_always,
        task_brief=(
            "Write a project overview that orients a new engineer in 2 minutes. "
            "Cover purpose, what the system does end-to-end, primary technologies, "
            "and the major subsystems. Cite source files for every concrete claim."
        ),
        body_outline=(
            "Purpose & one-line summary",
            "What it does (3–6 bullets, each cited)",
            "Primary technologies & frameworks",
            "Major subsystems and how they relate",
            "Where to look first (entry points)",
        ),
        always_on=True,
    ),
    "setup": _spec(
        id="setup",
        title="Quick Start & Setup",
        diataxis="how-to",
        output_path_template=".aura/docs/setup.md",
        required_aggregations=("config_inventory", "env_var_inventory"),
        applicability_rule=_always,
        task_brief=(
            "Write a quick-start guide with concrete install + run steps "
            "derived from package manifests, env files, and README headings. "
            "Do not invent commands; cite the manifest where each command/var "
            "originates. Mark anything inferred as `_unverified:_`."
        ),
        body_outline=(
            "Prerequisites (runtimes, tools, versions)",
            "Install steps",
            "Required environment variables (table: var, secret_like, defining file)",
            "Run / dev / build / test commands",
            "Common pitfalls",
        ),
        always_on=True,
    ),
    "architecture-system": _spec(
        id="architecture-system",
        title="System Architecture",
        diataxis="explanation",
        output_path_template=".aura/docs/architecture/system.md",
        required_aggregations=("module_responsibility_map", "endpoint_catalog", "external_integrations", "workflow_traces"),
        applicability_rule=_always,
        task_brief=(
            "Describe the high-level architecture: layers, boundaries, "
            "request lifecycle, and how subsystems compose. Cite the modules "
            "or files where each layer lives. Use a textual diagram (ascii or "
            "mermaid) only when the structure is genuinely tree-like."
        ),
        body_outline=(
            "Bird's-eye view",
            "Layers / tiers (API, services, persistence, integrations, UI)",
            "Request → processing → response lifecycle (one walk-through)",
            "Cross-cutting concerns (auth, logging, error handling)",
            "External boundaries",
        ),
        always_on=True,
    ),
    "architecture-modules": _spec(
        id="architecture-modules",
        title="Module Map",
        diataxis="reference",
        output_path_template=".aura/docs/architecture/modules.md",
        required_aggregations=("module_responsibility_map",),
        applicability_rule=_has_modules,
        task_brief=(
            "Catalog packages/top-level modules. For each: purpose, key "
            "responsibilities, exported symbols, and key incoming/outgoing "
            "dependencies. One subsection per package."
        ),
        body_outline=(
            "Index of packages",
            "Per-package: purpose, exports, dependencies (fan_in/fan_out), top callees",
        ),
        always_on=True,
    ),
    "architecture-flow": _spec(
        id="architecture-flow",
        title="Workflows & Data Flow",
        diataxis="explanation",
        output_path_template=".aura/docs/architecture/flow.md",
        required_aggregations=("workflow_traces", "endpoint_catalog", "data_model_graph", "external_integrations"),
        applicability_rule=_has_workflows,
        task_brief=(
            "Document the most important end-to-end workflows. For each, walk "
            "from entry point through the layers it touches: env reads, model "
            "writes, external calls. Pick at most the 6 most representative."
        ),
        body_outline=(
            "Workflow index (table)",
            "Per-workflow: trigger, steps, env reads, models touched, external calls",
        ),
        always_on=True,
    ),
    "config": _spec(
        id="config",
        title="Configuration & Environment",
        diataxis="reference",
        output_path_template=".aura/docs/config.md",
        required_aggregations=("config_inventory", "env_var_inventory"),
        applicability_rule=_always,
        task_brief=(
            "Document every configuration source and environment variable. "
            "Group by file. Mark secret-like vars and call out defaults."
        ),
        body_outline=(
            "Config files (table: path, kind, key concerns)",
            "Environment variables (table: var, secret_like, sites, defining file)",
            "Feature flags / toggles (if any)",
        ),
        always_on=True,
    ),
    "error-handling": _spec(
        id="error-handling",
        title="Error Handling & Failure Modes",
        diataxis="explanation",
        output_path_template=".aura/docs/error-handling.md",
        required_aggregations=("endpoint_catalog", "external_integrations"),
        applicability_rule=_always,
        task_brief=(
            "Describe the error model: where exceptions originate, how they "
            "propagate, what the user-facing surface looks like, and any retry/"
            "circuit-breaker behavior. If there is no central handler, say so "
            "and document what does exist."
        ),
        body_outline=(
            "Error taxonomy",
            "Where errors originate (cite handlers/wrappers)",
            "User-facing error surface",
            "Retry / fallback / timeout behavior",
        ),
        always_on=True,
    ),
    "glossary": _spec(
        id="glossary",
        title="Glossary",
        diataxis="reference",
        output_path_template=".aura/docs/glossary.md",
        required_aggregations=("module_responsibility_map", "data_model_graph"),
        applicability_rule=_always,
        task_brief=(
            "Extract domain-specific terms from module names, model names, "
            "and existing READMEs. Define each in 1–2 lines. Do not invent "
            "terms that have no source backing."
        ),
        body_outline=("Term — short definition (alphabetical)",),
        always_on=True,
    ),
    "adrs": _spec(
        id="adrs",
        title="Architectural Decisions",
        diataxis="explanation",
        output_path_template=".aura/docs/adrs.md",
        required_aggregations=("module_responsibility_map", "external_integrations"),
        applicability_rule=_always,
        task_brief=(
            "List architectural decisions inferable from the code: choice of "
            "framework, persistence layer, integration patterns, layering. For "
            "each: decision, evidence (cite source), and an inferred rationale "
            "marked `_unverified:_` since the rationale is interpretation."
        ),
        body_outline=("Decision — Evidence — Inferred rationale",),
        always_on=True,
    ),
    # ---- Backend conditional (5) -------------------------------------
    "api-endpoints": _spec(
        id="api-endpoints",
        title="API Reference — Endpoints",
        diataxis="reference",
        output_path_template=".aura/docs/api/endpoints.md",
        required_aggregations=("endpoint_catalog",),
        applicability_rule=_has_endpoints,
        task_brief=(
            "Produce a complete API reference. Group endpoints by URL prefix. "
            "For every endpoint: method, path, params, response model, status "
            "code, auth dependencies, and a one-line description. Every "
            "endpoint in the supplied catalog MUST appear at least once."
        ),
        body_outline=(
            "Index (table of all endpoints)",
            "Per-group sections with per-endpoint details",
        ),
    ),
    "api-models": _spec(
        id="api-models",
        title="API Reference — Data Models",
        diataxis="reference",
        output_path_template=".aura/docs/api/models.md",
        required_aggregations=("data_model_graph",),
        applicability_rule=_has_models,
        task_brief=(
            "Document every data model: fields, types, constraints, table name "
            "(for ORM models), relationships. Group by `kind` (pydantic / "
            "sqlalchemy / dataclass)."
        ),
        body_outline=(
            "Index of models",
            "Per-model section with field table",
            "Relationship diagram (textual)",
        ),
    ),
    "auth-security": _spec(
        id="auth-security",
        title="Auth & Security",
        diataxis="reference",
        output_path_template=".aura/docs/auth-security.md",
        required_aggregations=("auth_security_view", "env_var_inventory"),
        applicability_rule=_has_protected_or_secrets,
        task_brief=(
            "Document authentication and security posture: protected endpoints, "
            "auth dependencies in use, secret env vars, oauth flows if any."
        ),
        body_outline=(
            "Authentication mechanisms",
            "Auth dependencies (table)",
            "Protected endpoints (table)",
            "Secret-like env vars",
            "OAuth signals (if present)",
        ),
    ),
    "background-jobs": _spec(
        id="background-jobs",
        title="Background Jobs & Async Processes",
        diataxis="reference",
        output_path_template=".aura/docs/background-jobs.md",
        required_aggregations=("background_jobs_view",),
        applicability_rule=_has_jobs,
        task_brief=(
            "Document scheduled jobs, queues, workers, and async tasks. For "
            "each: type, trigger/schedule, file:line."
        ),
        body_outline=(
            "Index of jobs (table)",
            "Per-job details",
        ),
    ),
    "external-integrations": _spec(
        id="external-integrations",
        title="External Integrations",
        diataxis="reference",
        output_path_template=".aura/docs/external-integrations.md",
        required_aggregations=("external_integrations",),
        applicability_rule=_has_integrations,
        task_brief=(
            "Document third-party integrations: HTTP clients, DB drivers, "
            "AI providers, observability, etc. Group by category."
        ),
        body_outline=(
            "Integration index (by category)",
            "Per-integration: name, evidence, where it is used",
        ),
    ),
    # ---- Frontend conditional (3) -------------------------------------
    "frontend-pages": _spec(
        id="frontend-pages",
        title="Page Map",
        diataxis="reference",
        output_path_template=".aura/docs/frontend/pages.md",
        required_aggregations=("frontend_view",),
        applicability_rule=_has_pages,
        task_brief=(
            "List every routed page/screen in the frontend with its URL, "
            "component, and source location. Include unrouted top-level views "
            "if any."
        ),
        body_outline=("Routes table", "Per-route description"),
    ),
    "frontend-components": _spec(
        id="frontend-components",
        title="Component Tree",
        diataxis="reference",
        output_path_template=".aura/docs/frontend/components.md",
        required_aggregations=("frontend_view",),
        applicability_rule=_has_components,
        task_brief=(
            "Inventory the major UI components, grouped by directory. For each, "
            "its file and exported names."
        ),
        body_outline=("Component index", "By-directory listing"),
    ),
    "frontend-state": _spec(
        id="frontend-state",
        title="State Management",
        diataxis="explanation",
        output_path_template=".aura/docs/frontend/state.md",
        required_aggregations=("frontend_view",),
        applicability_rule=_has_state,
        task_brief=(
            "Describe how state is managed: stores, contexts, hooks, where "
            "data lives, and how updates flow."
        ),
        body_outline=("State stores", "Patterns in use", "Where each store is consumed"),
    ),
    # ---- CLI / library / IaC / ML (5) ---------------------------------
    "cli-commands": _spec(
        id="cli-commands",
        title="Command Reference",
        diataxis="reference",
        output_path_template=".aura/docs/cli/commands.md",
        required_aggregations=("cli_view",),
        applicability_rule=_has_cli,
        task_brief=(
            "Document each CLI command: name, file:line, description from "
            "docstring, and inferred arguments."
        ),
        body_outline=("Command index", "Per-command details"),
    ),
    "library-public-api": _spec(
        id="library-public-api",
        title="Public API",
        diataxis="reference",
        output_path_template=".aura/docs/library/public-api.md",
        required_aggregations=("module_responsibility_map", "data_model_graph"),
        applicability_rule=_is_library,
        task_brief=(
            "Document the public API: top-level exports, signatures, intended "
            "usage. Group by package."
        ),
        body_outline=("Public exports", "Per-symbol signature + brief usage"),
    ),
    "iac-resources": _spec(
        id="iac-resources",
        title="Infrastructure Resources",
        diataxis="reference",
        output_path_template=".aura/docs/iac/resources.md",
        required_aggregations=("iac_view",),
        applicability_rule=_has_iac,
        task_brief=(
            "Document infrastructure resources detected: terraform resources, "
            "k8s manifests, dockerfiles."
        ),
        body_outline=("Resources by kind", "Per-resource location"),
    ),
    "ml-model-cards": _spec(
        id="ml-model-cards",
        title="Model Cards",
        diataxis="reference",
        output_path_template=".aura/docs/ml/models.md",
        required_aggregations=("ml_view",),
        applicability_rule=_has_ml,
        task_brief="Document ML model files: framework, intended use, source location.",
        body_outline=("Models by framework",),
    ),
    "ml-pipeline-dag": _spec(
        id="ml-pipeline-dag",
        title="Pipeline DAG",
        diataxis="explanation",
        output_path_template=".aura/docs/ml/pipelines.md",
        required_aggregations=("ml_view",),
        applicability_rule=_has_ml,
        task_brief="Describe data/training pipelines: stages, dependencies, entry points.",
        body_outline=("Pipelines", "Per-pipeline DAG"),
    ),
    # ---- Per-entity deep-dive specs (extensible — orchestrator expands
    # one PlannedDoc per matching entity in the aggregations) -------------
    "data-model-detail": _spec(
        id="data-model-detail",
        title="Data Model",
        diataxis="reference",
        output_path_template=".aura/docs/data-models/{slug}.md",
        required_aggregations=("data_model_graph",),
        applicability_rule=_has_models,
        task_brief=(
            "Document ONE data model in depth. Lead with a `**Canonical Locator:**` "
            "line, then a one-paragraph description, then a `**Fields**` table "
            "(name | type | constraints | description), then `**Validators**` and "
            "`**Relationships**` if any. Conclude with `**See also**` listing "
            "related models as relative `.md` links."
        ),
        body_outline=(
            "Canonical Locator",
            "Description",
            "Fields (table)",
            "Constraints / Validators",
            "Relationships",
            "See also",
        ),
        always_on=False,
        extensible=True,
    ),
    "env-var-detail": _spec(
        id="env-var-detail",
        title="Environment Variable",
        diataxis="reference",
        output_path_template=".aura/docs/env-vars/{slug}.md",
        required_aggregations=("env_var_inventory", "config_inventory"),
        applicability_rule=_always,
        task_brief=(
            "Document ONE environment variable: purpose, where it is read, "
            "expected format with at least one concrete example, default if "
            "any, and a Security Considerations subsection. If secret_like, "
            "warn against committing it."
        ),
        body_outline=(
            "Overview",
            "Usage (where it is read)",
            "Format & examples",
            "Default behavior",
            "Security considerations",
        ),
        always_on=False,
        extensible=True,
    ),
    "endpoint-detail": _spec(
        id="endpoint-detail",
        title="API Endpoint",
        diataxis="reference",
        output_path_template=".aura/docs/api/endpoints/{slug}.md",
        required_aggregations=("endpoint_catalog", "data_model_graph", "auth_security_view"),
        applicability_rule=_has_endpoints,
        task_brief=(
            "Document ONE API endpoint: method, path, auth, request params, "
            "response model. Include a SAMPLE request and response as fenced "
            "JSON code blocks (mark `_unverified:_` if synthesized). Link to "
            "the response_model doc as a relative `.md` link when available."
        ),
        body_outline=(
            "Endpoint summary (method · path · auth)",
            "Request parameters",
            "Sample request",
            "Response schema",
            "Sample response",
            "Errors",
        ),
        always_on=False,
        extensible=True,
    ),
    "config-file-detail": _spec(
        id="config-file-detail",
        title="Config File",
        diataxis="reference",
        output_path_template=".aura/docs/config/{slug}.md",
        required_aggregations=("config_inventory", "env_var_inventory"),
        applicability_rule=_always,
        task_brief=(
            "Document ONE configuration file: kind, key entries, scripts, "
            "dependencies, and any env vars it defines. Cross-link any env "
            "vars defined here to their detail doc as relative `.md` links."
        ),
        body_outline=(
            "File summary (path · kind)",
            "Key entries",
            "Scripts (if any)",
            "Dependencies (if any)",
            "Defined environment variables",
        ),
        always_on=False,
        extensible=True,
    ),
    "module-flow-detail": _spec(
        id="module-flow-detail",
        title="Module Flow",
        diataxis="explanation",
        output_path_template=".aura/docs/modules/{slug}.md",
        required_aggregations=("module_responsibility_map", "endpoint_catalog", "workflow_traces"),
        applicability_rule=_has_modules,
        task_brief=(
            "Walk through ONE significant module / package: its purpose, the "
            "key flows that pass through it, the symbols it exports, and "
            "incoming/outgoing call edges. Add ONE Mermaid `sequenceDiagram` "
            "or `flowchart` only when a real flow benefits from it."
        ),
        body_outline=(
            "Purpose",
            "Exported symbols",
            "Key flows (per-flow walkthrough)",
            "Incoming / outgoing dependencies",
        ),
        always_on=False,
        extensible=True,
    ),
    # ---- Coverage / meta-doc -----------------------------------------
    "coverage-report": _spec(
        id="coverage-report",
        title="Documentation Coverage Report",
        diataxis="reference",
        output_path_template=".aura/docs/reports/coverage.md",
        required_aggregations=(),  # populated post-hoc by orchestrator
        applicability_rule=_always,
        task_brief="Auto-rendered from coverage stats; no LLM call.",
        body_outline=(),
        always_on=True,
    ),
}


def expand_extensible_plan(
    snapshot: RepoSnapshot,
    summary: dict[str, Any],
    aggs: ProjectAggregations,
) -> list[dict[str, Any]]:
    """Enumerate per-entity instances for extensible doc-type specs.

    Returns one entry per entity that should become a PlannedDoc:
    ``{"doc_type_id", "title", "target_path", "entity_focus", "priority"}``.
    The orchestrator materializes these into PlannedDoc objects after the
    LLM planner has chosen its registered doc-types.
    """
    out: list[dict[str, Any]] = []

    # Data models — one detail doc per model
    for m in aggs.data_model_graph.models:
        slug = _slug(m.name)
        out.append({
            "doc_type_id": "data-model-detail",
            "title": m.name,
            "target_path": f".aura/docs/data-models/{slug}.md",
            "entity_focus": {"kind": "data_model", "key": m.artifact_id, "name": m.name},
            "priority": 70,
        })

    # Env vars
    for v in aggs.env_var_inventory:
        slug = _slug(v.var)
        out.append({
            "doc_type_id": "env-var-detail",
            "title": v.var,
            "target_path": f".aura/docs/env-vars/{slug}.md",
            "entity_focus": {"kind": "env_var", "key": v.var, "name": v.var},
            "priority": 65,
        })

    # Endpoints — one per endpoint, capped at 60 to keep run cost sane
    endpoint_count = 0
    for group in aggs.endpoint_catalog:
        for e in group.endpoints:
            if endpoint_count >= 60:
                break
            slug = _slug(f"{e.method.lower()}-{e.path}")
            out.append({
                "doc_type_id": "endpoint-detail",
                "title": f"{e.method} {e.path}",
                "target_path": f".aura/docs/api/endpoints/{slug}.md",
                "entity_focus": {
                    "kind": "endpoint",
                    "key": f"{e.method} {e.path}",
                    "method": e.method,
                    "path": e.path,
                    "handler_qn": e.handler_qn,
                },
                "priority": 60,
            })
            endpoint_count += 1

    # Config files
    for c in aggs.config_inventory:
        slug = _slug(c.path)
        out.append({
            "doc_type_id": "config-file-detail",
            "title": c.path,
            "target_path": f".aura/docs/config/{slug}.md",
            "entity_focus": {"kind": "config_file", "key": c.path, "name": c.path},
            "priority": 55,
        })

    # Modules — top 8 by fan_in to limit doc count on big monorepos.
    # Dedup by package_path so two clustered entries don't create twin docs.
    seen_pkgs: set[str] = set()
    top_modules = sorted(aggs.module_responsibility_map, key=lambda m: -m.fan_in)[:8]
    for m in top_modules:
        pkg = m.package_path or ""
        if pkg in seen_pkgs:
            continue
        seen_pkgs.add(pkg)
        slug = _slug(pkg or m.cluster_name or "module")
        # Title prefers the unique package path so docs in the sidebar stay
        # distinct. Cluster name is informational and shown as a suffix.
        if pkg and m.cluster_name and m.cluster_name != pkg:
            title = f"{pkg} ({m.cluster_name})"
        else:
            title = pkg or m.cluster_name or slug
        out.append({
            "doc_type_id": "module-flow-detail",
            "title": title,
            "target_path": f".aura/docs/modules/{slug}.md",
            "entity_focus": {"kind": "module", "key": pkg, "name": pkg},
            "priority": 50,
        })

    return out


def _slug(text: str) -> str:
    import re
    s = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "")).strip("-").lower()
    return s or "item"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def applicable_doc_types(
    snapshot: RepoSnapshot,
    summary: dict[str, Any],
    aggs: ProjectAggregations,
) -> list[DocTypeSpec]:
    return [
        spec
        for spec in DOC_TYPE_REGISTRY.values()
        if spec.applicability_rule(snapshot, summary, aggs)
    ]


def required_doc_type_ids(
    snapshot: RepoSnapshot,
    summary: dict[str, Any],
    aggs: ProjectAggregations,
) -> list[str]:
    return [
        spec.id
        for spec in DOC_TYPE_REGISTRY.values()
        if spec.always_on and spec.applicability_rule(snapshot, summary, aggs)
    ]


def get_spec(doc_type_id: str) -> DocTypeSpec | None:
    return DOC_TYPE_REGISTRY.get(doc_type_id)


def make_extra_spec(
    doc_type_id: str,
    title: str,
    diataxis: DiataxisType,
    target_path: str,
    required_aggregations: tuple[str, ...],
    task_brief: str,
    body_outline: tuple[str, ...] = (),
) -> DocTypeSpec:
    """Construct a runtime spec for an LLM-proposed `extra:<slug>` doc type."""
    if not doc_type_id.startswith("extra:"):
        raise ValueError(f"extra doc_type_id must start with 'extra:': {doc_type_id}")
    return DocTypeSpec(
        id=doc_type_id,
        title=title,
        diataxis=diataxis,
        output_path_template=target_path,
        required_aggregations=tuple(required_aggregations),
        applicability_rule=_always,
        task_brief=task_brief,
        body_outline=tuple(body_outline),
        always_on=False,
        extensible=True,
    )
