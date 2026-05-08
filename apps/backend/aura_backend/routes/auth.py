from __future__ import annotations
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import get_session
from ..deps import current_user
from ..models import GithubOAuthToken, User
from ..services.github_oauth import (
    GithubOAuthError,
    exchange_code_for_token,
    fetch_github_user,
)


router = APIRouter(prefix="/api/v1/auth/github", tags=["github-link"])
logger = logging.getLogger(__name__)


_STATE_AUDIENCE = "github_oauth_state"


def _encode_state(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "aud": _STATE_AUDIENCE,
        "nonce": secrets.token_urlsafe(16),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_state(token: str) -> int:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        audience=_STATE_AUDIENCE,
    )
    return int(payload["sub"])


@router.get("/start")
async def github_link_start(user: User = Depends(current_user)):
    logger.info("github link start", extra={"user_id": user.id, "event": "github_link_start"})
    if not settings.github_client_id:
        raise HTTPException(status_code=500, detail="github_oauth_not_configured")

    state = _encode_state(user.id)
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "scope": settings.github_oauth_scope,
            "state": state,
            "redirect_uri": settings.github_oauth_redirect_uri,
        }
    )
    auth_url = f"https://github.com/login/oauth/authorize?{query}"
    return JSONResponse({"auth_url": auth_url})


@router.get("/callback")
async def github_link_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    logger.info("github link callback", extra={"event": "github_link_callback"})
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing_code_or_state")

    try:
        user_id = _decode_state(state)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=400, detail="invalid_state") from exc

    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")

    try:
        access_token = await exchange_code_for_token(
            settings.github_client_id,
            settings.github_client_secret,
            code,
            settings.github_oauth_redirect_uri,
        )
        github_user = await fetch_github_user(access_token)
    except GithubOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - upstream
        raise HTTPException(status_code=502, detail="github_oauth_upstream_error") from exc

    user.github_user_id = str(github_user["id"])
    user.login = github_user["login"]

    oauth_row = (
        await session.execute(select(GithubOAuthToken).where(GithubOAuthToken.user_id == user.id))
    ).scalar_one_or_none()
    if oauth_row:
        oauth_row.access_token = access_token
    else:
        session.add(GithubOAuthToken(user_id=user.id, access_token=access_token))
    await session.commit()
    logger.info("github link success", extra={"user_id": user.id, "event": "github_link_success"})

    redirect = settings.frontend_url.rstrip("/") + "/?github_linked=1"
    res = Response(status_code=302)
    res.headers["Location"] = redirect
    return res
