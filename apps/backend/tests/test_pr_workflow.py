from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

from httpx import ASGITransport, AsyncClient

from aura_backend.main import app
from aura_backend.models import DocDiff, PrAnalysisRun, PullRequest
from aura_backend.routes import webhooks as webhook_routes
from aura_backend.services import github_prs, pr_analysis


def _github_signature(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"
def test_pull_request_webhook_runs_analysis_and_comment(monkeypatch):
    async def _run():
        secret = "webhook-secret"
        monkeypatch.setattr(webhook_routes.settings, "github_webhook_secret", secret)

        calls: list[tuple[str, int]] = []

        async def _fake_upsert_pr(payload):
            assert payload["pull_request"]["number"] == 17
            return 91

        async def _fake_analyze(session_factory, pull_request_id):
            calls.append(("analyze", pull_request_id))

        async def _fake_comment(session_factory, pull_request_id):
            calls.append(("comment", pull_request_id))

        monkeypatch.setattr(webhook_routes, "_upsert_pr", _fake_upsert_pr)
        monkeypatch.setattr(webhook_routes, "analyze_pull_request", _fake_analyze)
        monkeypatch.setattr(webhook_routes, "post_or_update_review_comment", _fake_comment)

        payload = {
            "action": "opened",
            "repository": {
                "id": "1001",
                "full_name": "octo/widgets",
                "default_branch": "main",
                "owner": {"login": "octo"},
                "name": "widgets",
            },
            "pull_request": {"number": 17},
        }
        body = json.dumps(payload).encode("utf-8")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/webhooks/github",
                content=body,
                headers={
                    "content-type": "application/json",
                    "x-github-event": "pull_request",
                    "x-hub-signature-256": _github_signature(secret, body),
                },
            )

        assert response.status_code == 200
        assert response.json() == {"status": "accepted", "pull_request_id": 91}
        assert calls == [("analyze", 91), ("comment", 91)]

    asyncio.run(_run())


def test_pull_request_review_approval_webhook_creates_docs_followup(monkeypatch):
    async def _run():
        secret = "review-secret"
        monkeypatch.setattr(webhook_routes.settings, "github_webhook_secret", secret)

        async def _fake_upsert_pr(payload):
            assert payload["pull_request"]["number"] == 17
            return 73

        async def _fake_docs_followup(session_factory, pull_request_id):
            return {
                "status": "ready",
                "pull_request_id": pull_request_id,
                "docs_pull_request": {"number": 301, "url": "https://example.test/pull/301", "title": "docs: refresh Aura docs for PR #17"},
            }

        monkeypatch.setattr(webhook_routes, "_upsert_pr", _fake_upsert_pr)
        monkeypatch.setattr(webhook_routes, "create_or_update_docs_followup_pr", _fake_docs_followup)

        payload = {
            "action": "submitted",
            "review": {"state": "approved"},
            "repository": {
                "id": "1001",
                "full_name": "octo/widgets",
                "default_branch": "main",
                "owner": {"login": "octo"},
                "name": "widgets",
            },
            "pull_request": {"number": 17},
        }
        body = json.dumps(payload).encode("utf-8")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/webhooks/github",
                content=body,
                headers={
                    "content-type": "application/json",
                    "x-github-event": "pull_request_review",
                    "x-hub-signature-256": _github_signature(secret, body),
                },
            )

        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
        assert response.json()["pull_request_id"] == 73
        assert response.json()["docs_followup"]["docs_pull_request"]["number"] == 301

    asyncio.run(_run())


def test_docs_pr_body_summarizes_generated_changes():
    pr = PullRequest(number=7, title="Refine checkout flow", base_ref="main", head_ref="feature/checkout-flow", head_sha="head-sha-1234567890")
    pr_run = PrAnalysisRun(impact_summary={"severity_counts": {"critical": 1, "warning": 2, "info": 0}})
    diffs = [
        DocDiff(doc_path=".aura/docs/project-overview.md"),
        DocDiff(doc_path=".aura/docs/index.md"),
    ]

    body = github_prs._docs_pr_body(pr, pr_run, diffs)

    assert "Source PR: #7 - Refine checkout flow" in body
    assert "Base branch: `main`" in body
    assert "Documentation changes generated: 2" in body
    assert "Critical impacts: 1" in body
    assert "` .aura/docs/project-overview.md`" not in body
    assert "`.aura/docs/project-overview.md`" in body


def test_fallback_review_comment_mentions_flows_and_docs():
    impact = {
        "severity_counts": {"critical": 1, "warning": 2, "info": 0},
        "added": [{"name": "CheckoutService", "category": "module"}],
        "modified": [{"name": "POST /checkout", "category": "endpoint"}],
        "removed": [],
        "impacted_neighbors": [{"name": "Payment Flow"}],
        "affected_flows": [{"name": "Checkout Flow"}],
        "documentation_changes": {"added": 0, "modified": 1, "removed": 0},
    }

    body = pr_analysis._comment_body(
        impact,
        [{"doc_path": ".aura/docs/project-overview.md", "change_type": "modified"}],
    )

    assert body.startswith("<!-- aura-pr-review -->")
    assert "### Key Changes" in body
    assert "### Affected Flows" in body
    assert "- Checkout Flow" in body
    assert "Approve the PR or confirm docs follow-up" in body
