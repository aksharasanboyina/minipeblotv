#!/usr/bin/env bash
# Peblo TV Mini — one-command launcher for the full local stack.
# Starts (or reuses already-running) Postgres, the API, the CMS, and the Viewer.
# Safe to run repeatedly: any service already up on its port is skipped.
set -u

PGBIN="$HOME/.local/opt/peblo-pgsql/pgsql/bin"
PGDATA="$HOME/.local/opt/peblo-pgdata"
LOG_DIR="$HOME/.local/opt"
PG_LOG="$LOG_DIR/peblo-postgres.log"
API_LOG="$LOG_DIR/peblo-api.log"
CMS_LOG="$LOG_DIR/peblo-cms.log"
VIEWER_LOG="$LOG_DIR/peblo-viewer.log"

ROOT="$(cd "$(dirname "$0")" && pwd)"

port_open() { (exec 3<>"/dev/tcp/localhost/$1") 2>/dev/null; }

start_postgres() {
  if port_open 5432; then echo "  [skip] Postgres already up on :5432"; return; fi
  if [ ! -x "$PGBIN/postgres.exe" ]; then
    echo "  [err] Postgres binaries not found at $PGBIN — run the one-time setup first (see README)."
    exit 1
  fi
  if [ ! -d "$PGDATA" ]; then
    echo "  [err] Postgres data cluster not found at $PGDATA — run the one-time setup first (see README)."
    exit 1
  fi
  rm -f "$PGDATA/postmaster.pid"
  echo "  [start] Postgres (:5432) ..."
  (nohup "$PGBIN/postgres.exe" -D "$PGDATA" -p 5432 >>"$PG_LOG" 2>&1 &)
  sleep 4
  if port_open 5432; then
    echo "  [ok] Postgres up"
  else
    echo "  [err] Postgres failed to start — see $PG_LOG"
    exit 1
  fi
}

start_api() {
  if port_open 8000; then echo "  [skip] API already up on :8000"; return; fi
  local PY="$ROOT/backend/.venv312/Scripts/python.exe"
  if [ ! -x "$PY" ]; then
    echo "  [err] Backend venv not found ($PY) — create it with Python 3.12 and pip install -r backend/requirements.txt"
    exit 1
  fi
  echo "  [start] API (:8000) ... (seeds + auto-publishes on first boot)"
  (cd "$ROOT/backend" && nohup "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >>"$API_LOG" 2>&1 &)
  for _ in $(seq 1 40); do sleep 2; port_open 8000 && break; done
  if port_open 8000; then
    echo "  [ok] API up"
  else
    echo "  [err] API failed to start — see $API_LOG"
    exit 1
  fi
}

start_frontend() {
  local name="$1" port="$2" dir="$3" log="$4"
  if port_open "$port"; then echo "  [skip] $name already up on :$port"; return; fi
  if [ ! -d "$ROOT/$dir/node_modules" ]; then
    echo "  [err] $dir/node_modules missing — run npm install in $dir first"
    exit 1
  fi
  echo "  [start] $name (:$port) ..."
  (cd "$ROOT/$dir" && nohup npm run dev >>"$log" 2>&1 &)
  for _ in $(seq 1 30); do sleep 1; port_open "$port" && break; done
  if port_open "$port"; then
    echo "  [ok] $name up"
  else
    echo "  [warn] $name not responding yet — check $log"
  fi
}

echo "Starting Peblo TV Mini stack ..."
start_postgres
start_api
start_frontend "CMS"    3000 cms    "$CMS_LOG"
start_frontend "Viewer" 3001 viewer "$VIEWER_LOG"
echo
echo "============================================"
echo "  Viewer (kids app) -> http://localhost:3001  (kids@peblo.tv / peblo123)"
echo "  CMS (admin tool)  -> http://localhost:3000  (admin@peblo.tv)"
echo "  API docs          -> http://localhost:8000/docs"
echo "============================================"