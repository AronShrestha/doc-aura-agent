from pathlib import Path

import pytest

from aura_backend.analysis.agents.orchestrator import run_documentation_agents
from aura_backend.analysis.agents.planner import run_doc_planner_agent
from aura_backend.analysis.agents.vlm_context import run_vlm_context_agent
from aura_backend.analysis.types import ExtractedArtifact, ExtractedEdge, RepoSnapshot, SourceFile


class FakeLLM:
    def __init__(self, verifier_passed=True):
        self.verifier_passed = verifier_passed
        self.calls = []

    async def complete(self, messages, *, max_tokens=None, temperature=0.2):
        self.calls.append(messages[0]["content"])
        system = messages[0]["content"]
        if "Repo Analyst Agent" in system:
            return '{"architecture_summary":"FastAPI API","frameworks":["fastapi"],"risk_areas":[],"artifact_groups":[],"human_docs_summary":"","media_assets_summary":"","documentation_opportunities":["api docs"]}'
        if "Doc Planner Agent" in system:
            return '{"rationale":"plan","docs":[{"doc_id":"project-doc","title":"Project Overview","category":"project","diataxis_type":"explanation","target_path":".aura/docs/project-overview.md","source_artifact_ids":[],"uses_vlm_context":false,"priority":100,"writer":"system","rationale":"baseline"}]}'
        if "Verifier Agent" in system:
            if self.verifier_passed:
                return '{"passed":true,"citation_coverage":1.0,"unsupported_claims":0,"section_completeness":1.0,"issues":[]}'
            return '{"passed":false,"citation_coverage":0.2,"unsupported_claims":2,"section_completeness":0.5,"issues":["unsupported_claim"]}'
        return "# Generated\n\nUseful documentation.\n\n## Source Provenance\n\n- main.py:1"


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


@pytest.mark.asyncio
async def test_planner_returns_structured_plan(tmp_path):
    snapshot = _snapshot(tmp_path)
    plan = await run_doc_planner_agent(FakeLLM(), snapshot, [_endpoint_artifact()], {"architecture_summary": "api"}, [])
    assert plan.docs
    assert any(doc.target_path == ".aura/docs/project-overview.md" for doc in plan.docs)
    assert any(doc.source_artifact_ids == ["endpoint-1"] for doc in plan.docs)


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
async def test_verifier_failure_blocks_agent_workflow(tmp_path):
    snapshot = _snapshot(tmp_path)
    with pytest.raises(RuntimeError, match="agent_verification_failed"):
        await run_documentation_agents(
            snapshot,
            [_endpoint_artifact()],
            [],
            {"artifact_counts": {"endpoint": 1}, "parse_errors": []},
            FakeLLM(verifier_passed=False),
            None,
            vlm_enabled=False,
        )
