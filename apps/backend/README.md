# Aura Backend

Run locally:

```bash
cd apps/backend
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
uv run uvicorn aura_backend.main:app --reload --port 8001
```

Required env vars for real GitHub auth/linking:

```bash
cat > .env <<'EOF'
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GITHUB_OAUTH_REDIRECT_URI=http://localhost:8001/api/v1/auth/github/callback
FRONTEND_URL=http://localhost:5173
EOF
```

The backend auto-loads `apps/backend/.env` on startup.
