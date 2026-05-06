from pydantic import BaseModel
import os
from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / ".env")
load_dotenv(BASE_DIR / ".env")


def _load_github_private_key() -> str:
    key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "").strip()
    if key_path:
        p = Path(key_path).expanduser()
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    return os.getenv("GITHUB_APP_PRIVATE_KEY", "")


class Settings(BaseModel):
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_format: str = os.getenv("LOG_FORMAT", "text")
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./aura.db")
    github_client_id: str = os.getenv("GITHUB_CLIENT_ID", "")
    github_client_secret: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    github_oauth_scope: str = os.getenv("GITHUB_OAUTH_SCOPE", "read:user user:email")
    github_oauth_redirect_uri: str = os.getenv("GITHUB_OAUTH_REDIRECT_URI", "http://localhost:8001/api/v1/auth/github/callback")
    github_app_id: str = os.getenv("GITHUB_APP_ID", "")
    github_app_slug: str = os.getenv("GITHUB_APP_SLUG", "aura-demo")
    allow_stateless_install_callback: bool = os.getenv("ALLOW_STATELESS_INSTALL_CALLBACK", "true").lower() == "true"
    github_app_private_key_path: str = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "")
    github_app_private_key: str = _load_github_private_key()
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://129.212.188.166:8000/v1")
    llm_model: str = os.getenv("LLM_MODEL", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "90"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    vlm_enabled: bool = os.getenv("VLM_ENABLED", "false").lower() == "true"
    vlm_base_url: str = os.getenv("VLM_BASE_URL", os.getenv("LLM_BASE_URL", "http://129.212.188.166:8000/v1"))
    vlm_model: str = os.getenv("VLM_MODEL", os.getenv("LLM_MODEL", "TinyLlama/TinyLlama-1.1B-Chat-v1.0"))
    vlm_api_key: str = os.getenv("VLM_API_KEY", os.getenv("LLM_API_KEY", ""))
    vlm_timeout_seconds: int = int(os.getenv("VLM_TIMEOUT_SECONDS", "180"))
    vlm_max_tokens: int = int(os.getenv("VLM_MAX_TOKENS", "2048"))
    agent_max_artifacts: int = int(os.getenv("AGENT_MAX_ARTIFACTS", "120"))
    verifier_enabled: bool = os.getenv("VERIFIER_ENABLED", "false").lower() in ("1", "true", "yes")
    github_webhook_secret: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")


settings = Settings()
