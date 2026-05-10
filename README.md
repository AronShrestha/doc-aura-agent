# doc-aura-agent

> Aura is an AI-powered codebase intelligence platform that turns GitHub repositories into living architecture maps, searchable docs, and PR impact insights.

# Aura Hackathon Prototype

This repo includes an implementation scaffold for:

- GitHub sign-in and GitHub App installation linking
- Repo picker and analysis trigger
- Async worker-driven code analysis pipeline
- Generated documentation index / sections / search APIs
- Read-only MCP query server
- Minimal React onboarding UI

## Why

Fast-moving teams ship code faster than docs can keep up. Once docs go stale, developers stop trusting them, onboarding slows, and bugs creep in. Aura treats documentation as a **byproduct of code changes**:

- Initial run analyzes the repo and generates structured docs (architecture, API reference, key workflows).
- Each PR triggers a **delta analysis** — only impacted docs are recomputed and a **doc diff** is posted alongside the code diff.
- An **interactive impact graph** shows which artifacts and docs the PR touches.
- An **MCP server** exposes the resulting knowledge graph to IDEs and agents (Claude Code, Cursor, Windsurf).

The differentiator is not "generate docs once" — it is "**maintain docs continuously, surface impact per PR**".

---

## System architecture

```mermaid
flowchart LR
  User([User])
  subgraph Client[Frontend · apps/frontend]
    UI[React + Vite UI]
  end
  subgraph Server[Backend API · apps/backend]
    API[FastAPI routes]
    Q[(Run queue)]
    Pipe[Analysis pipeline]
    PRO[PR orchestrator<br/>LangGraph]
  end
  subgraph MCP[MCP server · apps/mcp_server]
    FM[FastMCP tools]
  end
  DB[(SQLite + FTS5)]
  GH[(GitHub<br/>OAuth · App · Webhooks)]
  LLM[(LLM<br/>OpenAI-compatible)]
  EMB[(Qwen embedder)]

  User --> UI
  UI <-->|JWT REST| API
  API --> Q --> Pipe
  GH -->|webhook| API --> PRO
  Pipe --> LLM
  Pipe --> EMB
  Pipe --> DB
  PRO --> LLM
  PRO --> DB
  PRO -->|PR comment| GH
  API --> GH
  FM --> DB
  FM --> EMB
  IDE([Claude Code · Cursor]) <-->|stdio / SSE| FM
```

---

## Components

### Backend — `apps/backend/aura_backend/`

FastAPI app with async SQLAlchemy, an in-process run queue, and a LangGraph PR orchestrator.

| Area | Path | Purpose |
|---|---|---|
| Entry | `main.py` | App init, CORS, routers, startup hooks |
| Config | `config.py` | Env-var settings (GitHub, LLM, embedder, DB) |
| Routes | `routes/auth.py` | JWT sessions, email + password |
| | `routes/github.py` | OAuth + GitHub App install flows |
| | `routes/analysis.py` | `/repos/analyze`, `/runs/{id}`, `/docs/search`, `/docs/chat` |
| | `routes/users.py` | Profile, repos, PR list |
| | `routes/webhooks.py` | GitHub `pull_request` events |
| Services | `services/queue.py` | `RunQueue` — asyncio FIFO dispatcher |
| | `services/pr_orchestrator.py` | LangGraph state machine for PRs |
| | `services/pr_analysis.py` | Base/head diff, mismatch detection |
| | `services/shadow_pr.py` | Materialize doc updates as shadow PRs |
| | `services/github_oauth.py` | OAuth token exchange |
| | `services/github_app.py` | App JWT + installation tokens |
| Pipeline | `analysis/pipeline.py` | 5-stage orchestrator |
| | `analysis/snapshot.py` | AST walking, file graph |
| | `analysis/extractors.py` | Symbols, routes, models, env vars |
| | `analysis/aggregators.py` | Endpoint catalogs, data-model rollups |
| | `analysis/graph.py` | Artifact dependency graph |
| Agents | `analysis/agents/orchestrator.py` | Drives multi-agent doc gen |
| | `analysis/agents/repo_analyst.py` | Architecture overview |
| | `analysis/agents/planner.py` | Plan doc set |
| | `analysis/agents/writers.py` | Draft sections |
| | `analysis/agents/verifier.py` | Verify citations |
| | `analysis/agents/pr_reviewer.py` | PR comment generator |
| | `analysis/agents/dashboard.py` | Dashboard metadata |
| | `analysis/agents/doc_updater.py` | Suggest doc updates from code diffs |
| | `analysis/agents/docs_chat.py` | Q&A over generated docs (RAG) |
| | `analysis/agents/embedding.py` | Qwen embedder client |
| Data | `models.py` | 14 SQLAlchemy tables |
| | `schemas.py` | Pydantic request/response |

### Frontend — `apps/frontend/src/`

React 18 + Vite, React Query for server state, ReactFlow + D3 for graphs, Mermaid for diagrams.

| Area | Path | Purpose |
|---|---|---|
| Entry | `main.jsx`, `App.jsx` | Routes, auth guard, navbar |
| Auth | `auth.jsx` | AuthProvider context |
| API | `api.js` | Axios + JWT interceptor + React-Query hooks |
| Views | `views/Home.jsx` | Repo dashboard |
| | `views/DocsDashboard.jsx` | Run progress + activity log |
| | `views/ImpactGraph.jsx` | Artifact dependency graph |
| | `views/RepoLayout.jsx` · `RepoTabs.jsx` | Repo nested tabs |
| | `views/RepoPrsView.jsx` | PR list with live polling |
| | `views/PrDiffView.jsx` | Side-by-side doc + code diffs |
| | `views/Login.jsx` · `Signup.jsx` | Auth screens |
| Components | `Mermaid.jsx` | Render Mermaid from markdown |
| | `DocChat.jsx` | Chat over docs |
| | `DocDiff.jsx` | Side-by-side doc change view |
| | `AgentActivity.jsx` · `RunProgress.jsx` | Live progress UI |
| | `TierChip.jsx` · `VerifiedBadge.jsx` | Impact / verification badges |

Key routes:

```
/login · /signup
/                              → Home (repo list)
/runs/:runId                   → Docs dashboard (live)
/runs/:runId/graph             → Impact graph
/repos/:repoId/docs            → Generated docs explorer
/repos/:repoId/graph           → Symbol graph
/repos/:repoId/prs             → PRs list
/repos/:repoId/prs/:prId       → PR detail (doc + code diffs)
```

### MCP server — `apps/mcp_server/`

FastMCP server, queries the same SQLite DB. Transports: **stdio** (Claude Code / Cursor / Windsurf) and **SSE** (web).

| Tool | Purpose |
|---|---|
| `search_docs` | Hybrid FTS5 + vector search (RRF ranking, Qwen embeddings) |
| `get_doc` | Fetch full doc by slug or `artifact_id` |
| `get_symbol` | Symbol metadata with verified line ranges |
| `get_dependents` | BFS blast radius (callers / dependents) |
| `get_impact` | PR impact summary + doc diffs |

---

## Analysis pipeline (5 stages)

```mermaid
flowchart LR
  A[Acquire<br/>git clone → .aura/checkouts] --> B[Parse<br/>AST · file graph]
  B --> C[Extract<br/>functions · classes<br/>routes · models · env]
  C --> D[Synthesize<br/>multi-agent LLM<br/>Repo-analyst → Planner<br/>Writers → Verifier]
  D --> E[Persist<br/>docs · embeddings<br/>diffs · mappings]
```

Driven by `apps/backend/aura_backend/analysis/pipeline.py`. PR runs reuse stages 1–3 only (static delta), then jump to compare + comment.

---

## PR analysis flow (LangGraph state machine)

```mermaid
stateDiagram-v2
  [*] --> upsert_pr_run
  upsert_pr_run --> analyze_base
  upsert_pr_run --> analyze_head
  analyze_base --> compare
  analyze_head --> compare
  compare --> dashboard_agent
  dashboard_agent --> persist
  persist --> comment_agent
  comment_agent --> post_comment
  post_comment --> [*]
```

`apps/backend/aura_backend/services/pr_orchestrator.py` defines the graph. `analyze_base` / `analyze_head` run in parallel.

---

## End-to-end sequence

### Initial repo analysis

```mermaid
sequenceDiagram
  actor U as User
  participant FE as Frontend
  participant API as Backend API
  participant Q as RunQueue
  participant P as Pipeline
  participant L as LLM
  participant DB as DB

  U->>FE: Pick repo · click Analyze
  FE->>API: POST /repos/analyze
  API->>DB: Insert AnalysisRun(status=queued)
  API->>Q: enqueue(run_id)
  API-->>FE: {run_id}
  loop poll every 3s
    FE->>API: GET /runs/{id}
    API-->>FE: status · stage · activity
  end
  Q->>P: run_analysis(run_id)
  P->>P: Acquire · Parse · Extract
  P->>L: Synthesize sections
  L-->>P: Drafts + citations
  P->>DB: Persist Artifacts · Docs · Embeddings
  P-->>API: status=completed
```

### PR webhook → impact comment

```mermaid
sequenceDiagram
  participant GH as GitHub
  participant API as Backend API
  participant O as PR Orchestrator
  participant L as LLM
  participant DB as DB

  GH->>API: POST /webhooks/github/pull_request
  API->>DB: Upsert PullRequest · PrAnalysisRun
  API->>O: trigger(pr_run_id)
  par
    O->>O: analyze_base
  and
    O->>O: analyze_head
  end
  O->>O: compare (build DocDiffs · mismatch flags)
  O->>L: Generate dashboard + PR comment
  O->>DB: Persist DocDiff rows
  O->>GH: POST/PATCH issue comment
```

---

## Data model

```mermaid
erDiagram
  USER ||--o{ SESSION : has
  USER ||--o{ GITHUB_OAUTH_TOKEN : has
  USER ||--o{ GITHUB_INSTALLATION : owns
  GITHUB_INSTALLATION ||--o{ REPO : contains
  REPO ||--o{ ANALYSIS_RUN : triggers
  REPO ||--o{ PULL_REQUEST : tracks
  ANALYSIS_RUN ||--o{ ARTIFACT : extracts
  ARTIFACT ||--o{ ARTIFACT_EDGE : depends_on
  ANALYSIS_RUN ||--o{ GENERATED_DOC : produces
  GENERATED_DOC ||--o{ DOC_SECTION : contains
  ARTIFACT ||--o{ DOC_MAPPING : maps_to
  GENERATED_DOC ||--o{ DOC_MAPPING : maps_to
  PULL_REQUEST ||--o{ PR_ANALYSIS_RUN : analyzed_by
  PR_ANALYSIS_RUN ||--o{ DOC_DIFF : produces
  ANALYSIS_RUN ||--o{ DRIFT_REPORT : reports

  USER {
    int id PK
    string email
    string github_user_id
    string display_name
  }
  REPO {
    int id PK
    string full_name
    string default_branch
    int installation_id FK
  }
  ANALYSIS_RUN {
    int id PK
    int repo_id FK
    string status
    string stage
    int progress
    json activity_log
  }
  ARTIFACT {
    int id PK
    int run_id FK
    string kind
    string symbol_id
    string file_path
    int line_start
    int line_end
  }
  GENERATED_DOC {
    int id PK
    int run_id FK
    string slug
    string content_hash
    text markdown
    blob embedding
  }
  PR_ANALYSIS_RUN {
    int id PK
    int pr_id FK
    int base_run_id FK
    int head_run_id FK
    string status
    string shadow_pr_url
  }
  DOC_DIFF {
    int id PK
    int pr_run_id FK
    string change_type
    string impact_tier
    text unified_diff
  }
```

Defined in `apps/backend/aura_backend/models.py`.

---

## Tech stack

**Backend** — FastAPI · SQLAlchemy (async) · Alembic-free migrations · LangGraph · Tree-sitter · OpenAI-compatible HTTP client · pytest

**Frontend** — React 18.3 · Vite 5.4 · React Router 6 · TanStack Query 5 · Axios · ReactFlow 11 · Dagre · D3-Force · Mermaid · react-markdown + remark-gfm · react-diff-viewer

**MCP** — FastMCP · SQLite FTS5 · Qwen-Embedding (optional) · stdio + SSE transports

**Storage** — SQLite (default), pluggable via `DATABASE_URL`

---

## Repo layout

```
.
├── apps/
│   ├── backend/      FastAPI · pipeline · agents · models
│   ├── frontend/     React + Vite UI
│   └── mcp_server/   FastMCP query server
├── scripts/          Helper scripts
├── prd.md            Product requirements
├── DOCUMENTATION_STANDARDS.md
├── documentation list.md
├── interactive graph.md
└── README.md
```

---

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

LLM + embedder configuration:

```bash
export LLM_BASE_URL=http://localhost:8000/v1
export LLM_API_KEY=...
export LLM_MODEL=...
# Optional — enables vector search in MCP + RAG chat
export EMBEDDING_BASE_URL=http://localhost:8000/v1
export EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
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

For stdio (Claude Code / Cursor / Windsurf), point your client at `python -m mcp_server` with `PYTHONPATH=../backend` and the same `DATABASE_URL` as the backend.
