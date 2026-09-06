#!/usr/bin/env bash
# Peblo TV Mini — stop the local stack (API, CMS, Viewer, then Postgres).
set -u

stop_port() {
  local port="$1"
  local pids
  pids=$(netstat -ano 2>/dev/null | grep LISTENING | grep -E ":$port\s" | awk '{print $NF}' | sort -u)
  if [ -z "$pids" ]; then
    echo "  [skip] nothing on :$port"
    return
  fi
  for pid in $pids; do
    echo "  [stop] killing PID $pid (:$port)"
    taskkill //F //PID "$pid" >/dev/null 2>&1 || true
  done
  sleep 1
}

echo "Stopping Peblo TV Mini stack ..."
stop_port 8000   # API
stop_port 3000   # CMS
stop_port 3001   # Viewer
stop_port 5432   # Postgres (last)
echo "Done. Data (Postgres cluster + backend/storage) is kept — run ./run.sh to start again."