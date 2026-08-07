#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT/.data/pids"
LOG_DIR="$ROOT/.data"
mkdir -p "$PID_DIR" "$LOG_DIR"

start() {
  local name="$1"
  local directory="$2"
  local command="$3"
  local pid_file="$PID_DIR/$name.pid"
  local log_file="$LOG_DIR/$name.log"

  if [[ -f "$pid_file" ]]; then
    local old_pid
    old_pid="$(cat "$pid_file")"
    if kill -0 "$old_pid" 2>/dev/null; then
      echo "$name already running (pid $old_pid)"
      return
    fi
    rm -f "$pid_file"
  fi

  (
    cd "$directory" || exit 1
    nohup bash -c "$command" >>"$log_file" 2>&1 &
    echo $! >"$pid_file"
  )
  sleep 0.2
  echo "started $name (pid $(cat "$pid_file"))"
}

start backend "$ROOT/backend" \
  ".venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

start frontend "$ROOT/frontend" \
  "npm run dev -- --hostname 127.0.0.1 --port 3000"

echo "Waiting for health endpoints..."
for i in $(seq 1 40); do
  cp_ok=$(curl -sf http://127.0.0.1:8000/health >/dev/null && echo 1 || echo 0)
  wc_ok=$(curl -sf http://127.0.0.1:3000/ >/dev/null && echo 1 || echo 0)
  if [[ "$cp_ok$wc_ok" == "11" ]]; then
    echo "READY: backend:8000 frontend:3000"
    exit 0
  fi
  sleep 2
done

echo "WARN: not all services healthy yet — check .data/*.log"
exit 1
