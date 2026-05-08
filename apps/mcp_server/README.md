# Aura MCP Server

Read-only Model Context Protocol server. Exposes the Aura analysis database
(generated docs, artifact graph, PR impact) to MCP-aware clients (Claude
Desktop, Claude Code, Cursor, Windsurf).

## Tools registered

| Tool             | Purpose                                                   |
|------------------|-----------------------------------------------------------|
| `search_docs`    | Hybrid FTS5 + vector search across the wiki (RRF blend)   |
| `get_doc`        | Fetch one doc by slug or artifact id                      |
| `get_symbol`     | Code artifact details with `file:line` citations          |
| `get_dependents` | Blast-radius lookup: who depends on this symbol           |
| `get_impact`     | Per-PR change summary (touched docs, tier counts)         |

## One-time setup

```bash
cd apps/mcp_server
uv venv
source .venv/bin/activate
uv pip install -e .
```

Run a backend analysis first so the SQLite DB has data:

```bash
cd apps/backend
uv run uvicorn aura_backend.main:app --reload --port 8001
# trigger an analysis from the dashboard at http://localhost:5173
```

## Smoke-test the launcher

```bash
./run.sh                            # boots stdio; exits when stdin closes
AURA_MCP_TRANSPORT=sse ./run.sh     # boots SSE on port 7338 for browser demo
```

You should see `aura mcp server ready` on stderr.

## Wire into Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "aura": {
      "command": "/Users/isharm/Playground/a/apps/mcp_server/run.sh"
    }
  }
}
```

Restart Claude Desktop. The five Aura tools appear under the 🔌 menu in any
chat. Try: *"Use the aura search_docs tool with repo_id=1 and query 'how
does authentication work'"*.

## Wire into Claude Code (CLI)

```bash
claude mcp add aura /Users/isharm/Playground/a/apps/mcp_server/run.sh
claude mcp list                     # confirm "aura" appears
```

Inside any `claude` session: `/mcp` lists active servers; the `aura` tools
become available to the model.

## Environment variables

| Var                  | Default                                                | Notes                              |
|----------------------|--------------------------------------------------------|------------------------------------|
| `AURA_DB_URL`        | `sqlite+aiosqlite:///<backend>/aura.db`                | Same DB the FastAPI backend writes |
| `AURA_MCP_TRANSPORT` | `stdio`                                                | `stdio` for editors, `sse` for web |
| `AURA_MCP_PORT`      | `7338`                                                 | SSE only                           |
| `EMBEDDING_BASE_URL` | unset                                                  | If unset, vector search is skipped — FTS still works |

## Architecture

```
Claude / Cursor / Windsurf
        │  (MCP stdio)
        ▼
  apps/mcp_server  ──reads──►  apps/backend/aura.db  (GeneratedDoc, Artifact, ArtifactEdge, PrAnalysisRun)
        │
        └─ FTS5 docs_fts table (built on first boot)
        └─ Qwen embedding vectors (optional — falls back to FTS)
```
