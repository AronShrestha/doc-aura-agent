from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import GithubInstallation, GithubOAuthToken
from ..routes.auth import current_user
from ..services.github import make_state
from ..services.github_app import (
    GithubAppError,
    build_app_jwt,
    create_installation_token,
    get_installation_metadata,
    list_installation_repositories,
)
from ..config import settings
from ..services.github_oauth import list_user_repositories

router = APIRouter(prefix="/api/v1/github", tags=["github"])
logger = logging.getLogger(__name__)


async def _upsert_installation_for_user(session: AsyncSession, user_id: int, installation_id: str) -> GithubInstallation:
    logger.info("github installation upsert requested", extra={"event": "github_installation_upsert"})
    existing = (await session.execute(
        select(GithubInstallation).where(
            GithubInstallation.user_id == user_id,
            GithubInstallation.installation_id == installation_id,
        )
    )).scalar_one_or_none()

    if existing:
        return existing

    try:
        app_jwt = build_app_jwt(settings.github_app_id, settings.github_app_private_key)
        meta = await get_installation_metadata(app_jwt, installation_id)
    except GithubAppError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="github_app_upstream_error") from exc

    row = GithubInstallation(
        user_id=user_id,
        installation_id=installation_id,
        account_login=meta["account_login"],
        account_type=meta["account_type"],
    )
    session.add(row)
    await session.commit()
    return row


@router.get("/connect/start")
async def github_connect_start(user=Depends(current_user)):
    logger.info("github app connect start requested", extra={"event": "github_connect_start"})
    if not settings.github_app_id or not settings.github_app_private_key:
        raise HTTPException(status_code=500, detail="github_app_not_configured")
    state = make_state()
    res = JSONResponse({
        "install_url": f"https://github.com/apps/{settings.github_app_slug}/installations/new?state={state}",
        "state": state,
    })
    res.set_cookie("aura_install_state", state, httponly=True, samesite="lax")
    return res


@router.get("/connect/callback")
async def github_connect_callback(
    request: Request,
    installation_id: str | None = None,
    setup_action: str | None = None,
    state: str | None = None,
    user=Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    logger.info("github app connect callback received", extra={"event": "github_connect_callback"})
    if not installation_id:
        raise HTTPException(status_code=400, detail="missing_installation_id")
    state_cookie = request.cookies.get("aura_install_state")
    if state_cookie and (not state or state != state_cookie):
        raise HTTPException(status_code=400, detail="invalid_state")
    if (not state_cookie or not state) and not settings.allow_stateless_install_callback:
        raise HTTPException(status_code=400, detail="missing_state")

    await _upsert_installation_for_user(session, user.id, installation_id)

    redirect_url = f"{settings.frontend_url}?github_installation_linked=1&installation_id={installation_id}"
    res = RedirectResponse(url=redirect_url, status_code=302)
    res.delete_cookie("aura_install_state")
    logger.info("github app connect callback succeeded", extra={"event": "github_connect_success"})
    return res


@router.post("/installations/link")
async def link_installation_by_id(installation_id: str, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.info("github installation link requested", extra={"event": "github_installation_link"})
    if not installation_id:
        raise HTTPException(status_code=400, detail="missing_installation_id")
    row = await _upsert_installation_for_user(session, user.id, installation_id)
    return {
        "status": "linked",
        "installation_id": row.installation_id,
        "account_login": row.account_login,
        "account_type": row.account_type,
    }


@router.get("/installations")
async def list_installations(user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.debug("github installations requested", extra={"event": "github_installations_list"})
    rows = (await session.execute(select(GithubInstallation).where(GithubInstallation.user_id == user.id))).scalars().all()
    return {
        "installations": [
            {
                "installation_id": r.installation_id,
                "account_login": r.account_login,
                "account_type": r.account_type,
            }
            for r in rows
        ]
    }


@router.get("/repos/oauth")
async def list_repos_oauth(user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.info("github oauth repos requested", extra={"event": "github_repos_oauth"})
    token_row = (await session.execute(select(GithubOAuthToken).where(GithubOAuthToken.user_id == user.id))).scalar_one_or_none()
    if not token_row:
        raise HTTPException(status_code=401, detail="github_oauth_token_missing")
    try:
        repos = await list_user_repositories(token_row.access_token)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="github_oauth_repo_fetch_failed") from exc
    return {"repos": repos}


@router.get("/repos")
async def list_repos(installation_id: str, user=Depends(current_user), session: AsyncSession = Depends(get_session)):
    logger.info("github app repos requested", extra={"event": "github_repos_app"})
    inst = (await session.execute(
        select(GithubInstallation).where(
            GithubInstallation.user_id == user.id,
            GithubInstallation.installation_id == installation_id,
        )
    )).scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=403, detail="installation_not_owned")

    try:
        app_jwt = build_app_jwt(settings.github_app_id, settings.github_app_private_key)
        installation_token = await create_installation_token(app_jwt, installation_id)
        repos = await list_installation_repositories(installation_token)
    except GithubAppError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="github_app_upstream_error") from exc
    return {"repos": repos}
