#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT/.data/pids"

stop_name() {
  local name="$1"
  local pid_file="$PID_DIR/$name.pid"
  [[ -f "$pid_file" ]] || return 0
  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    sleep 1
    kill -9 -- "-$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    echo "stopped $name"
  fi
  rm -f "$pid_file"
}

stop_name backend
stop_name frontend
# legacy pid names (pre D-011 / removed sample targets)
stop_name control-plane
stop_name web-console
stop_name sample-fe
stop_name sample-be

# Fallback port cleanup for orphaned children
for port in 8000 3000 5173 8080; do
  pids=$(lsof -tiTCP:$port -sTCP:LISTEN 2>/dev/null || true)
  if [[ -n "${pids:-}" ]]; then
    echo "$pids" | xargs -n1 kill 2>/dev/null || true
  fi
done
