# doc-aura-agent
Aura is an AI-powered codebase intelligence platform that turns GitHub repositories into living architecture maps, searchable docs, and PR impact insights.

# Aura Hackathon Prototype

This repo now includes an implementation scaffold for:
- GitHub sign-in and GitHub App installation linking
- Repo picker and analysis trigger
- Async worker-driven code analysis pipeline
- Generated documentation index/sections/search APIs
- Read-only MCP query server
- Minimal React onboarding UI

## Services

- Backend API: `apps/backend`
- Frontend UI: `apps/frontend`
- MCP server: `apps/mcp_server`

## Backend quickstart

```bash
cd apps/backend
uv venv
source .venv/bin/activate
uv pip install -e '.[dev]'
uv run uvicorn aura_backend.main:app --reload --port 8001
uv run pytest -q
```

GitHub auth configuration:

```bash
export GITHUB_CLIENT_ID=...
export GITHUB_CLIENT_SECRET=...
export GITHUB_OAUTH_REDIRECT_URI=http://localhost:8001/api/v1/auth/github/callback
export GITHUB_APP_ID=...
export GITHUB_APP_SLUG=your-github-app-slug
export GITHUB_APP_PRIVATE_KEY_PATH=/absolute/path/to/github-app.pem
# Optional fallback:
# export GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
export FRONTEND_URL=http://localhost:5173
```

## Frontend quickstart

```bash
cd apps/frontend
npm install
npm run dev
```

## MCP server quickstart

```bash
cd apps/mcp_server
uv venv
source .venv/bin/activate
uv pip install -e .
PYTHONPATH=../backend uv run uvicorn server:app --reload --port 8002
```
