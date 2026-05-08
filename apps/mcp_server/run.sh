#!/usr/bin/env bash
# Launch the Aura MCP server over stdio for Claude Desktop / Claude Code.
# Resolves all paths relative to this script so the launcher is location-
# independent. Override defaults via env vars before invoking.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS_ROOT="$(cd "$HERE/.." && pwd)"
BACKEND_DIR="$APPS_ROOT/backend"
VENV_PY="$HERE/.venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  echo "aura-mcp: venv missing — run: cd $HERE && uv venv && uv pip install -e ." >&2
  exit 1
fi

export PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}$BACKEND_DIR:$APPS_ROOT"
export AURA_DB_URL="${AURA_DB_URL:-sqlite+aiosqlite:///$BACKEND_DIR/aura.db}"
export AURA_MCP_TRANSPORT="${AURA_MCP_TRANSPORT:-stdio}"

exec "$VENV_PY" -m mcp_server "$@"
