from __future__ import annotations
from dataclasses import dataclass
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker

from .db import engine, ensure_columns
from .models import Base
from .services.queue import RunQueue
from .routes.auth import router as auth_router
from .routes.github import router as github_router
from .routes.analysis import router as analysis_router
from .routes.users import router as users_router
from .routes.webhooks import router as webhooks_router
from .config import settings
from .logging_config import configure_logging


configure_logging()
logger = logging.getLogger(__name__)


@dataclass
class AppState:
    queue: RunQueue


app = FastAPI(title="Aura API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)
app.include_router(auth_router)
app.include_router(github_router)
app.include_router(analysis_router)
app.include_router(webhooks_router)


@app.get("/api/v1/health")
async def health():
    logger.debug("health check", extra={"event": "health"})
    return {"status": "ok"}


@app.on_event("startup")
async def startup():
    logger.info("backend startup started", extra={"event": "startup"})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_columns(conn)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    app_state.queue = RunQueue(factory)
    await app_state.queue.start()
    logger.info("backend startup complete", extra={"event": "startup_complete"})


app_state = AppState(queue=RunQueue(async_sessionmaker(engine, expire_on_commit=False)))
