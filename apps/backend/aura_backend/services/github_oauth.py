from __future__ import annotations

import httpx


class GithubOAuthError(Exception):
    pass


async def exchange_code_for_token(client_id: str, client_secret: str, code: str, redirect_uri: str | None = None) -> str:
    payload: dict[str, str] = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    }
    if redirect_uri:
        payload["redirect_uri"] = redirect_uri

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    token = data.get("access_token")
    if not token:
        raise GithubOAuthError(data.get("error_description", "oauth_token_exchange_failed"))
    return token


async def fetch_github_user(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if "id" not in data or "login" not in data:
        raise GithubOAuthError("invalid_user_profile")
    return data


async def list_user_repositories(access_token: str) -> list[dict]:
    repos: list[dict] = []
    page = 1
    async with httpx.AsyncClient(timeout=20) as client:
        while True:
            resp = await client.get(
                "https://api.github.com/user/repos",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                params={
                    "per_page": 100,
                    "page": page,
                    "sort": "updated",
                    "affiliation": "owner,collaborator,organization_member",
                },
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1

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
