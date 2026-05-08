from __future__ import annotations
import logging
import random
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import current_user
from ..models import AnalysisRun, Repo, User
from ..schemas import (
    AuthResponse,
    DummyResponse,
    LoginRequest,
    MeResponse,
    MyReposResponse,
    RepoSummary,
    SignupRequest,
    UserPublic,
)
from ..services.auth import create_access_token, hash_password, verify_password


router = APIRouter(prefix="/api/v1", tags=["users"])
logger = logging.getLogger(__name__)


_DUMMY_MESSAGES = [
    "Aura agents are warming up.",
    "Dummy endpoint says hello from the docs layer.",
    "Nothing to see here except a lucky number.",
]


@router.get("/dummy/random", response_model=DummyResponse)
async def random_dummy():
    return DummyResponse(
        message=random.choice(_DUMMY_MESSAGES),
        lucky_number=random.randint(1000, 9999),
    )


@router.post("/auth/signup", response_model=AuthResponse)
async def signup(req: SignupRequest, session: AsyncSession = Depends(get_session)):
    email = req.email.lower()
    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="email_already_registered")

    user = User(
        email=email,
        password_hash=hash_password(req.password),
        display_name=req.display_name,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    token = create_access_token(user.id)
    logger.info("user signup", extra={"user_id": user.id, "event": "user_signup"})
 
    return AuthResponse(
        access_token=token,
        user=UserPublic(id=user.id, email=user.email, display_name=user.display_name),
    )


@router.post("/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_session)):
    email = req.email.lower()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid_credentials")

    token = create_access_token(user.id)
    logger.info("user login", extra={"user_id": user.id, "event": "user_login"})
    return AuthResponse(
        access_token=token,
        user=UserPublic(id=user.id, email=user.email, display_name=user.display_name),
    )


@router.get("/auth/me", response_model=MeResponse)
async def me(user: User = Depends(current_user)):
    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        github_linked=bool(user.github_user_id),
        github_login=user.login,
    )


@router.get("/me/repos", response_model=MyReposResponse)
async def my_repos(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    repos = (
        await session.execute(select(Repo).where(Repo.user_id == user.id).order_by(Repo.id.desc()))
    ).scalars().all()
    summaries: list[RepoSummary] = []
    for repo in repos:
        run = (
            await session.execute(
                select(AnalysisRun)
                .where(
                    AnalysisRun.repo_id == repo.id,
                    AnalysisRun.is_pr_run.is_(False),
                    AnalysisRun.branch == repo.default_branch,
                )
                .order_by(AnalysisRun.id.desc())
            )
        ).scalars().first()
        latest = None
        if run:
            last_msg = None
            if run.activity:
                tail = run.activity[-1] if isinstance(run.activity, list) else None
                if isinstance(tail, dict):
                    last_msg = tail.get("message")
            latest = {
                "id": run.id,
                "status": run.status,
                "stage": run.stage,
                "progress": run.progress,
                "updated_at": run.updated_at.isoformat() if run.updated_at else None,
                "last_message": last_msg,
            }
        summaries.append(
            RepoSummary(
                repo_id=repo.id,
                github_repo_id=repo.github_repo_id,
                full_name=repo.full_name,
                default_branch=repo.default_branch,
                latest_run=latest,
            )
        )
    return MyReposResponse(repos=summaries)
