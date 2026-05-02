#!/usr/bin/env bash
#
# Local development runner. Sets up venvs and starts the panel + agent
# with overridable env vars so you can hack on Lumen without going
# through the full installer.
#
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_DIR="${DEV_DIR:-$ROOT/.dev}"
mkdir -p "$DEV_DIR/data/db" "$DEV_DIR/data/servers" "$DEV_DIR/logs"

JWT_SECRET="${LUMEN_JWT_SECRET:-$(openssl rand -hex 48)}"
API_KEY="${LUMEN_API_KEY:-$(openssl rand -hex 32)}"
NODE_KEY="${LUMEN_NODE_KEY:-$(openssl rand -hex 32)}"

export LUMEN_JWT_SECRET="$JWT_SECRET"
export LUMEN_API_KEY="$API_KEY"
export LUMEN_NODE_KEY="$NODE_KEY"
export LUMEN_DATABASE_URL="sqlite:///$DEV_DIR/data/db/panel.db"
export LUMEN_DATA_DIR="$DEV_DIR/data"
export LUMEN_LOG_DIR="$DEV_DIR/logs"
export LUMEN_PORT=8000
export LUMEN_AGENT_URL="http://127.0.0.1:8081"
export LUMEN_AGENT_PORT=8081
export LUMEN_PANEL_URL="http://127.0.0.1:8000"
export LUMEN_GAME_PORT_START=25565
export LUMEN_GAME_PORT_END=25600

cd "$ROOT/backend"
[[ -d .venv ]] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

cd "$ROOT/agent"
[[ -d .venv ]] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

cd "$ROOT/setup-ui"
[[ -d .venv ]] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

cat <<EOF

Dev secrets (save these):
  LUMEN_JWT_SECRET=$JWT_SECRET
  LUMEN_API_KEY=$API_KEY
  LUMEN_NODE_KEY=$NODE_KEY

Run in three separate terminals (with the env above exported), or use 'just':

  # Setup UI (port 8080) - only needed first time:
  cd setup-ui && .venv/bin/python server.py

  # Panel (port 8000):
  cd backend && .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  # Agent (port 8081):
  cd agent && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8081 --reload

EOF
