from pathlib import Path

import pytest

from aura_backend.analysis.agents.orchestrator import run_documentation_agents
from aura_backend.analysis.agents.planner import run_project_doc_planner_agent
from aura_backend.analysis.agents.vlm_context import run_vlm_context_agent
from aura_backend.analysis.aggregators import build_project_aggregations
from aura_backend.analysis.types import ExtractedArtifact, ExtractedEdge, RepoSnapshot, SourceFile


class FakeLLM:
    def __init__(self, verifier_passed=True):
        self.verifier_passed = verifier_passed
        self.calls = []

    async def complete(self, messages, *, max_tokens=None, temperature=0.2):
        self.calls.append(messages[0]["content"])
        system = messages[0]["content"]
        if "Repo Analyst Agent" in system:
            return (
                '{"architecture_summary":"FastAPI API","frameworks":["fastapi"],'
                '"risk_areas":[],"artifact_groups":[],"human_docs_summary":"",'
                '"media_assets_summary":"","documentation_opportunities":["api docs"]}'
            )
        if "Project Doc Planner" in system:
            return (
                '{"codebase_profile":{"type":"api","primary_language":"python",'
                '"summary":"FastAPI service","subprojects":[]},'
                '"doc_plan":[{"doc_type_id":"overview","title":"Project Overview","rationale":"baseline"},'
                '{"doc_type_id":"api-endpoints","title":"API Reference","rationale":"endpoints"}],'
                '"rationale":"plan"}'
            )
        if "Verifier Agent" in system:
            if self.verifier_passed:
                return '{"passed":true,"citation_coverage":1.0,"unsupported_claims":0,"section_completeness":1.0,"issues":[]}'
            return '{"passed":false,"citation_coverage":0.2,"unsupported_claims":2,"section_completeness":0.5,"issues":["unsupported_claim"]}'
        # Project doc writer fallback — Markdown body with one citation.
        return (
            "# Project Overview\n\n"
            "Doc AURA is a FastAPI service [verified: main.py:L1-L4].\n\n"
            "## Source Provenance\n\n- main.py:L1-L4\n"
        )


class FakeVLM:
    def __init__(self):
        self.paths = []

    async def describe_image(self, image_path: Path, prompt: str):
        self.paths.append(image_path)
        return '{"description":"A UI screenshot","documentation_relevance":"Useful for usage docs","confidence":0.9}'


def _snapshot(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    source = SourceFile(
        path="main.py",
        language="python",
        loc=4,
        source_hash="abc",
        text="from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health(): return {}\n",
        top_level_symbols=["health"],
        imports=["fastapi"],
    )
    return RepoSnapshot(root=root, repo_id=42, repo_sha="sha", files=[source], frameworks=["fastapi"])


def _endpoint_artifact():
    return ExtractedArtifact(
        artifact_id="endpoint-1",
        category="endpoint",
        name="GET /health",
        canonical_locator="GET /health",
        source_file="main.py",
        source_line_start=3,
        source_line_end=4,
        payload={"method": "GET", "path": "/health"},
    )


def _module_artifact():
    return ExtractedArtifact(
        artifact_id="module-main",
        category="module",
        name="main",
        canonical_locator="main",
        source_file="main.py",
        source_line_start=1,
        source_line_end=4,
        payload={"language": "python", "loc": 4, "imports": ["fastapi"], "exports": ["health"]},
    )


@pytest.mark.asyncio
async def test_project_planner_returns_profile_and_plan(tmp_path):
    snapshot = _snapshot(tmp_path)
    artifacts = [_endpoint_artifact(), _module_artifact()]
    summary = {"artifact_counts": {"endpoint": 1, "module": 1}, "parse_errors": []}
    aggs = build_project_aggregations(snapshot, artifacts, [], summary)
    plan, spec_by_id = await run_project_doc_planner_agent(
        FakeLLM(), snapshot, summary, aggs, {"architecture_summary": "api"}, []
    )
    assert plan.codebase_profile is not None
    assert plan.codebase_profile.type == "api"
    # Always-on docs auto-injected by _ensure_minimum
    doc_type_ids = {d.doc_type_id for d in plan.docs}
    assert "overview" in doc_type_ids
    assert "api-endpoints" in doc_type_ids
    assert "config" in doc_type_ids  # always-on
    # Specs returned for every chosen doc
    for d in plan.docs:
        assert d.doc_type_id in spec_by_id


@pytest.mark.asyncio
async def test_vlm_disabled_skips_media(tmp_path):
    snapshot = _snapshot(tmp_path)
    (snapshot.root / "screenshot.png").write_bytes(b"fake")
    contexts = await run_vlm_context_agent(snapshot, FakeVLM(), enabled=False)
    assert contexts == []


@pytest.mark.asyncio
async def test_vlm_enabled_sends_repo_media(tmp_path):
    snapshot = _snapshot(tmp_path)
    (snapshot.root / "screenshot.png").write_bytes(b"fake")
    vlm = FakeVLM()
    contexts = await run_vlm_context_agent(snapshot, vlm, enabled=True)
    assert len(contexts) == 1
    assert vlm.paths[0].name == "screenshot.png"


@pytest.mark.asyncio
async def test_verifier_failure_blocks_agent_workflow(tmp_path, monkeypatch):
    snapshot = _snapshot(tmp_path)
    from aura_backend import config as cfg
    monkeypatch.setattr(cfg.settings, "verifier_enabled", True)
    with pytest.raises(RuntimeError, match="agent_verification_failed"):
        await run_documentation_agents(
            snapshot,
            [_endpoint_artifact(), _module_artifact()],
            [],
            {"artifact_counts": {"endpoint": 1}, "parse_errors": []},
            FakeLLM(verifier_passed=False),
            None,
            vlm_enabled=False,
        )


@pytest.mark.asyncio
async def test_documentation_run_emits_project_docs(tmp_path):
    snapshot = _snapshot(tmp_path)
    docs, quality = await run_documentation_agents(
        snapshot,
        [_endpoint_artifact(), _module_artifact()],
        [],
        {"artifact_counts": {"endpoint": 1, "module": 1}, "parse_errors": []},
        FakeLLM(verifier_passed=True),
        None,
        vlm_enabled=False,
    )
    paths = {d.slug_path for d in docs}
    # Hierarchical layout under .aura/docs/
    assert ".aura/docs/index.md" in paths
    assert ".aura/docs/overview.md" in paths
    assert ".aura/docs/api/endpoints.md" in paths
    # Manifest carries codebase_profile + tree
    manifest = quality["manifest"]
    assert manifest["codebase_profile"]["type"] == "api"
    assert manifest["tree"], "tree should be populated"
