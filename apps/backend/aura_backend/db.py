from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from .config import settings

engine = create_async_engine(settings.database_url, future=True)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


async def ensure_columns(conn) -> None:
    if conn.dialect.name != "sqlite":
        return

    async def _existing(table: str) -> set[str]:
        cols = await conn.execute(text(f"PRAGMA table_info({table})"))
        return {row[1] for row in cols.fetchall()}

    runs_cols = await _existing("analysis_runs")
    if "user_id" not in runs_cols:
        await conn.execute(text("ALTER TABLE analysis_runs ADD COLUMN user_id INTEGER"))
    if "activity" not in runs_cols:
        await conn.execute(text("ALTER TABLE analysis_runs ADD COLUMN activity TEXT"))

    user_cols = await _existing("users")
    if user_cols:
        if "email" not in user_cols:
            await conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255)"))
        if "password_hash" not in user_cols:
            await conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) DEFAULT ''"))
        if "display_name" not in user_cols:
            await conn.execute(text("ALTER TABLE users ADD COLUMN display_name VARCHAR(255)"))

    repo_cols = await _existing("repos")
    if repo_cols and "user_id" not in repo_cols:
        await conn.execute(text("ALTER TABLE repos ADD COLUMN user_id INTEGER"))
