from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Any

import httpx
import jwt


class GithubAppError(Exception):
    pass


def _normalize_private_key(private_key: str) -> str:
    return private_key.replace("\\n", "\n")


def build_app_jwt(app_id: str, private_key: str) -> str:
    if not app_id or not private_key:
        raise GithubAppError("github_app_not_configured")
    now = datetime.now(UTC)
    payload = {
        "iat": int((now - timedelta(seconds=60)).timestamp()),
        "exp": int((now + timedelta(minutes=9)).timestamp()),
        "iss": app_id,
    }
    return jwt.encode(payload, _normalize_private_key(private_key), algorithm="RS256")


async def create_installation_token(app_jwt: str, installation_id: str) -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    if resp.status_code >= 400:
        raise GithubAppError(f"installation_token_failed:{resp.status_code}:{resp.text}")
    token = resp.json().get("token")
    if not token:
        raise GithubAppError("installation_token_missing")
    return token


async def get_installation_metadata(app_jwt: str, installation_id: str) -> dict[str, str]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"https://api.github.com/app/installations/{installation_id}",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    if resp.status_code >= 400:
        raise GithubAppError(f"installation_metadata_failed:{resp.status_code}:{resp.text}")
    data = resp.json()
    account = data.get("account") or {}
    return {
        "account_login": account.get("login", f"installation_{installation_id}"),
        "account_type": account.get("type", "Unknown"),
    }


async def list_installation_repositories(installation_token: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://api.github.com/installation/repositories",
            headers={
                "Authorization": f"Bearer {installation_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    if resp.status_code >= 400:
        raise GithubAppError(f"list_repos_failed:{resp.status_code}:{resp.text}")
    repos = resp.json().get("repositories", [])
    return [
        {
            "id": str(r["id"]),
            "full_name": r["full_name"],
            "owner": r["owner"]["login"],
            "name": r["name"],
            "default_branch": r.get("default_branch", "main"),
            "private": bool(r.get("private", False)),
        }
        for r in repos
    ]
