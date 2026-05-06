# Aura MCP Read-only Server

Run:

```bash
cd apps/mcp_server
uv venv
source .venv/bin/activate
uv pip install -e .
PYTHONPATH=../backend uv run uvicorn server:app --reload --port 8002
```
