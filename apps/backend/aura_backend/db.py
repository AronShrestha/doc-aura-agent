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
    if "is_pr_run" not in runs_cols:
        await conn.execute(text("ALTER TABLE analysis_runs ADD COLUMN is_pr_run BOOLEAN DEFAULT 0"))

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

    pr_cols = await _existing("pull_requests")
    if pr_cols:
        if "html_url" not in pr_cols:
            await conn.execute(text("ALTER TABLE pull_requests ADD COLUMN html_url VARCHAR(500)"))
        if "merged" not in pr_cols:
            await conn.execute(text("ALTER TABLE pull_requests ADD COLUMN merged BOOLEAN DEFAULT 0"))

    pr_run_cols = await _existing("pr_analysis_runs")
    if pr_run_cols:
        if "code_patches" not in pr_run_cols:
            await conn.execute(text("ALTER TABLE pr_analysis_runs ADD COLUMN code_patches JSON"))
        if "mismatch_flags" not in pr_run_cols:
            await conn.execute(text("ALTER TABLE pr_analysis_runs ADD COLUMN mismatch_flags JSON"))
        if "dashboard_url" not in pr_run_cols:
            await conn.execute(text("ALTER TABLE pr_analysis_runs ADD COLUMN dashboard_url VARCHAR(500)"))
