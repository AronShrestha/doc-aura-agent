from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker

if __package__ in {None, ""}:
    # Support `uvicorn main:app` when launched from `apps/backend/aura_backend`.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from aura_backend.config import settings
    from aura_backend.db import engine
    from aura_backend.logging_config import configure_logging
    from aura_backend.models import Base
    from aura_backend.routes.analysis import router as analysis_router
    from aura_backend.routes.auth import router as auth_router
    from aura_backend.routes.github import router as github_router
    from aura_backend.routes.webhooks import router as webhooks_router
    from aura_backend.services.queue import RunQueue
else:
    from .config import settings
    from .db import engine
    from .logging_config import configure_logging
    from .models import Base
    from .routes.analysis import router as analysis_router
    from .routes.auth import router as auth_router
    from .routes.github import router as github_router
    from .routes.webhooks import router as webhooks_router
    from .services.queue import RunQueue


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

    factory = async_sessionmaker(engine, expire_on_commit=False)
    app_state.queue = RunQueue(factory)
    await app_state.queue.start()
    logger.info("backend startup complete", extra={"event": "startup_complete"})


@app.on_event("shutdown")
async def shutdown():
    logger.info("backend shutdown started", extra={"event": "shutdown"})
    await app_state.queue.stop()
    logger.info("backend shutdown complete", extra={"event": "shutdown_complete"})


app_state = AppState(queue=RunQueue(async_sessionmaker(engine, expire_on_commit=False)))
