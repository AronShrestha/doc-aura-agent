from __future__ import annotations
import logging
import secrets
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Response, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import User, Session, GithubOAuthToken
from ..config import settings
from ..services.github_oauth import exchange_code_for_token, fetch_github_user, GithubOAuthError

router = APIRouter(prefix="/api/v1/auth/github", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/start")
async def github_auth_start():
    logger.info("github oauth start requested", extra={"event": "github_auth_start"})
    if not settings.github_client_id:
        raise HTTPException(status_code=500, detail="github_oauth_not_configured")

    state = secrets.token_urlsafe(24)
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "scope": settings.github_oauth_scope,
            "state": state,
            "redirect_uri": settings.github_oauth_redirect_uri,
        }
    )
    auth_url = f"https://github.com/login/oauth/authorize?{query}"
    res = JSONResponse({"auth_url": auth_url})
    res.set_cookie("aura_auth_state", state, httponly=True, samesite="lax")
    return res


@router.get("/callback")
async def github_auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    logger.info("github oauth callback received", extra={"event": "github_auth_callback"})
    if not code:
        raise HTTPException(status_code=400, detail="missing_code")
    state_cookie = request.cookies.get("aura_auth_state")
    if not state or not state_cookie or state != state_cookie:
        raise HTTPException(status_code=400, detail="invalid_state")

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
    except Exception as exc:
        raise HTTPException(status_code=502, detail="github_oauth_upstream_error") from exc

    github_user_id = str(github_user["id"])
    login = github_user["login"]

    user = (await session.execute(select(User).where(User.github_user_id == github_user_id))).scalar_one_or_none()
    if not user:
        user = User(github_user_id=github_user_id, login=login)
        session.add(user)
        await session.flush()

    token = secrets.token_urlsafe(24)
    sess = Session(user_id=user.id, token=token)
    session.add(sess)

    oauth_row = (await session.execute(select(GithubOAuthToken).where(GithubOAuthToken.user_id == user.id))).scalar_one_or_none()
    if oauth_row:
        oauth_row.access_token = access_token
    else:
        session.add(GithubOAuthToken(user_id=user.id, access_token=access_token))
    await session.commit()
    logger.info("github oauth callback succeeded", extra={"event": "github_auth_success"})

    res = Response(status_code=302)
    res.headers["Location"] = settings.frontend_url
    res.set_cookie("aura_session", token, httponly=True, samesite="lax")
    res.delete_cookie("aura_auth_state")
    return res


async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    token = request.cookies.get("aura_session")
    if not token:
        raise HTTPException(status_code=401, detail="unauthorized")
    sess = (await session.execute(select(Session).where(Session.token == token))).scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=401, detail="unauthorized")
    user = (await session.execute(select(User).where(User.id == sess.user_id))).scalar_one()
    return user


@router.get("/me")
async def github_auth_me(user: User = Depends(current_user)):
    logger.debug("auth me requested", extra={"event": "github_auth_me"})
    return {"id": user.id, "login": user.login}
