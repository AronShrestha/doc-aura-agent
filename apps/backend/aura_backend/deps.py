from __future__ import annotations
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .models import User
from .services.auth import TokenError, decode_access_token


def _bearer_token(request: Request) -> str:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="unauthorized")
    return auth.split(" ", 1)[1].strip()


async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    token = _bearer_token(request)
    try:
        user_id = decode_access_token(token)
    except TokenError:
        raise HTTPException(status_code=401, detail="unauthorized")
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    return user
