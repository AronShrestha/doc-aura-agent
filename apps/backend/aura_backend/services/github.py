from __future__ import annotations
import secrets
from typing import Any


def make_state() -> str:
    return secrets.token_urlsafe(24)


def fake_installation_repos(installation_id: str) -> list[dict[str, Any]]:
    # Hackathon-safe stub. Replace with GitHub App installation token call.
    base = int(installation_id[-2:], 16) if installation_id and installation_id[-2:].isalnum() else 10
    return [
        {
            "id": str(base + 1),
            "full_name": "aura-demo/widgets-api",
            "owner": "aura-demo",
            "name": "widgets-api",
            "default_branch": "main",
            "private": False,
        },
        {
            "id": str(base + 2),
            "full_name": "aura-demo/payments-service",
            "owner": "aura-demo",
            "name": "payments-service",
            "default_branch": "main",
            "private": True,
        },
    ]
