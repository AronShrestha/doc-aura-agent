import asyncio
import secrets
import pytest
from httpx import AsyncClient, ASGITransport

from aura_backend.main import app
from aura_backend.db import engine, ensure_columns
from aura_backend.models import Base, AnalysisRun
from aura_backend.routes import auth as auth_routes
from aura_backend.routes import github as github_routes
from aura_backend.routes import analysis as analysis_routes
from aura_backend.analysis import pipeline as analysis_pipeline


async def _init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_columns(conn)


@pytest.mark.asyncio
async def test_health():
    await _init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_auth_and_analysis_flow():
    await _init_db()
    original_client_id = auth_routes.settings.github_client_id
    original_client_secret = auth_routes.settings.github_client_secret
    auth_routes.settings.github_client_id = "test-client"
    auth_routes.settings.github_client_secret = "test-secret"

    async def _fake_exchange(client_id, client_secret, code, redirect_uri):
        assert client_id == "test-client"
        assert client_secret == "test-secret"
        assert code == "abcdef123"
        return "gho_test_token"

    async def _fake_user(token):
        assert token == "gho_test_token"
        return {"id": 987654, "login": "real-gh-user"}

    auth_routes.exchange_code_for_token = _fake_exchange
    auth_routes.fetch_github_user = _fake_user
    async def _fake_oauth_repos(access_token):
        assert access_token == "gho_test_token"
        return [
            {
                "id": "1001",
                "full_name": "aura-demo/widgets-api",
                "owner": "aura-demo",
                "name": "widgets-api",
                "default_branch": "main",
                "private": False,
            }
        ]

    github_routes.list_user_repositories = _fake_oauth_repos
    analysis_routes.list_user_repositories = _fake_oauth_repos
    original_fetch = analysis_pipeline._fetch_repo_zip
    original_llm = analysis_pipeline._llm_chat

    async def _fake_fetch(repo, run, token):
        root = analysis_pipeline.CHECKOUT_ROOT / "test" / str(run.id) / "repo"
        root.mkdir(parents=True, exist_ok=True)
        (root / "main.py").write_text(
            "\n".join(
                [
                    "from fastapi import FastAPI",
                    "from pydantic import BaseModel",
                    "app = FastAPI()",
                    "class Widget(BaseModel):",
                    "    id: int",
                    "@app.get('/widgets/{widget_id}', response_model=Widget)",
                    "async def get_widget(widget_id: int):",
                    "    return Widget(id=widget_id)",
                ]
            ),
            encoding="utf-8",
        )
        return root

    async def _fake_llm(messages):
        system = messages[0]["content"]
        if "Repo Analyst Agent" in system:
            return '{"architecture_summary":"FastAPI service","frameworks":["fastapi"],"risk_areas":[],"artifact_groups":[],"human_docs_summary":"","media_assets_summary":"","documentation_opportunities":["api reference"]}'
        if "Project Doc Planner" in system:
            return (
                '{"codebase_profile":{"type":"api","primary_language":"python",'
                '"summary":"FastAPI service","subprojects":[]},'
                '"doc_plan":[{"doc_type_id":"overview","title":"Project Overview","rationale":"baseline"},'
                '{"doc_type_id":"api-endpoints","title":"API Reference","rationale":"endpoints"}],'
                '"rationale":"Document API and architecture."}'
            )
        if "Verifier Agent" in system:
            return '{"passed":true,"citation_coverage":1.0,"unsupported_claims":0,"section_completeness":1.0,"issues":[]}'
        return (
            "# Generated\n\nStatic documentation [verified: main.py:L1-L8].\n\n"
            "## Source Provenance\n\n- main.py:L1-L8\n"
        )

    analysis_pipeline._fetch_repo_zip = _fake_fetch
    analysis_pipeline._llm_chat = _fake_llm

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as client:
        s = await client.get("/api/v1/auth/github/start")
        assert s.status_code == 200
        auth_state = s.cookies.get("aura_auth_state")
        assert auth_state

        r = await client.get("/api/v1/auth/github/callback", params={"code": "abcdef123", "state": auth_state})
        assert r.status_code == 302
        cookie = r.cookies.get("aura_session")
        assert cookie

        headers = {"cookie": f"aura_session={cookie}"}

        r3 = await client.get("/api/v1/github/repos/oauth", headers=headers)
        assert r3.status_code == 200
        repo_id = r3.json()["repos"][0]["id"]

        r4 = await client.post(
            "/api/v1/repos/analyze",
            json={"github_repo_id": repo_id, "branch": "main"},
            headers=headers,
        )
        assert r4.status_code == 200
        run_id = r4.json()["run_id"]
        repo_row_id = r4.json()["repo_id"]

        status = "running"
        for _ in range(20):
            await asyncio.sleep(0.3)
            r5 = await client.get(f"/api/v1/runs/{run_id}", headers=headers)
            assert r5.status_code == 200
            status = r5.json()["status"]
            if status in {"succeeded", "failed"}:
                break
        assert status == "succeeded"

        r6 = await client.get(f"/api/v1/repos/{repo_row_id}/docs/index", headers=headers)
        assert r6.status_code == 200
        assert len(r6.json()["sections"]) > 0

        r7 = await client.get(f"/api/v1/repos/{repo_row_id}/artifacts?category=endpoint", headers=headers)
        assert r7.status_code == 200
        assert r7.json()["artifacts"][0]["name"] == "GET /widgets/{widget_id}"

        r8 = await client.get(f"/api/v1/repos/{repo_row_id}/graph", headers=headers)
        assert r8.status_code == 200
        assert len(r8.json()["nodes"]) > 0

    auth_routes.settings.github_client_id = original_client_id
    auth_routes.settings.github_client_secret = original_client_secret
    analysis_pipeline._fetch_repo_zip = original_fetch
    analysis_pipeline._llm_chat = original_llm


@pytest.mark.asyncio
async def test_llm_failure_marks_run_failed_without_fallback_docs():
    await _init_db()
    original_fetch = analysis_pipeline._fetch_repo_zip
    original_llm = analysis_pipeline._llm_chat

    async def _fake_fetch(repo, run, token):
        root = analysis_pipeline.CHECKOUT_ROOT / "test-fail" / str(run.id) / "repo"
        root.mkdir(parents=True, exist_ok=True)
        (root / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
        return root

    async def _failing_llm(messages):
        raise RuntimeError("llm_down")

    analysis_pipeline._fetch_repo_zip = _fake_fetch
    analysis_pipeline._llm_chat = _failing_llm

    from sqlalchemy import select
    from aura_backend.models import Repo, GithubOAuthToken, User
    from aura_backend.db import SessionLocal

    async with SessionLocal() as session:
        suffix = secrets.token_hex(6)
        user = User(github_user_id=f"llm-test-{suffix}", login="llm-test")
        session.add(user)
        await session.flush()
        session.add(GithubOAuthToken(user_id=user.id, access_token="token"))
        repo = Repo(github_repo_id=f"2002-{suffix}", full_name="aura-demo/llm-fail", default_branch="main", installation_id="oauth", owner="aura-demo", name="llm-fail")
        session.add(repo)
        await session.flush()
        run = AnalysisRun(repo_id=repo.id, status="queued", stage="queued", progress=0, branch="main")
        session.add(run)
        await session.commit()
        run_id = run.id

    await analysis_pipeline.run_analysis(run_id, analysis_pipeline.async_sessionmaker(engine, expire_on_commit=False))

    async with SessionLocal() as session:
        run = (await session.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalar_one()
        assert run.status == "failed"
        assert "llm_down" in run.error

    analysis_pipeline._fetch_repo_zip = original_fetch
    analysis_pipeline._llm_chat = original_llm
