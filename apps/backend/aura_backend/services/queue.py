from __future__ import annotations
import asyncio
import contextlib
import logging
from sqlalchemy.ext.asyncio import async_sessionmaker
from ..analysis.pipeline import run_analysis


logger = logging.getLogger(__name__)


class RunQueue:
    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory
        self._q: asyncio.Queue[int] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self):
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())
        logger.info("analysis queue started", extra={"event": "queue_started"})

    async def stop(self):
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            logger.info("analysis queue stopped", extra={"event": "queue_stopped"})

    async def enqueue(self, run_id: int):
        await self._q.put(run_id)
        logger.info("analysis run enqueued", extra={"run_id": run_id, "event": "queue_enqueue"})

    async def _loop(self):
        while True:
            run_id = await self._q.get()
            try:
                logger.info("analysis queue picked run", extra={"run_id": run_id, "event": "queue_dequeue"})
                await run_analysis(run_id, self._session_factory)
            except Exception:
                logger.exception("analysis queue run crashed", extra={"run_id": run_id, "event": "queue_error"})
            finally:
                self._q.task_done()
