#!/usr/bin/env bash
set -euo pipefail

# Start DigitalSec Platform (API + static web)
# - Creates venv, installs deps
# - Loads .env (creates from example if missing)
# - Ensures data folders
# - Starts API (uvicorn) and a static server for the SPA

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$ROOT_DIR"

echo "[start] Working dir: $PWD"

mkdir -p logs data data/reports

if [[ ! -d .venv ]]; then
  echo "[start] Creating virtualenv (.venv)"
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null || true

echo "[start] Installing/updating dependencies (requirements.txt)"
# Be resilient when offline: don't fail if pip cannot reach the network
if ! pip install -r requirements.txt >/dev/null 2>> logs/api.log; then
  echo "[warn] pip install failed or offline; continuing with existing virtualenv"
fi

if [[ ! -f .env ]]; then
  echo "[start] Creating .env from .env.example"
  cp .env.example .env
fi

# Load env vars and set safe defaults for local dev
set -a
source .env
# Use SQLite by default if not configured
DATABASE_URL="${DATABASE_URL:-sqlite:///./data/app.db}"
# Disable PDF generation locally unless explicitly enabled
REPORT_PDF="${REPORT_PDF:-false}"
# Enable scheduler by default only if user set it; otherwise disable to keep dev simple
ENABLE_SCHEDULER="${ENABLE_SCHEDULER:-0}"
export DATABASE_URL REPORT_PDF ENABLE_SCHEDULER
set +a

echo "[start] DATABASE_URL=$DATABASE_URL"
echo "[start] REPORT_PDF=$REPORT_PDF"

# Helper: wait for a log line (offline-safe)
wait_log() {
  local file="$1" pattern="$2" retries="${3:-120}" delay="${4:-0.5}"
  for ((i=0; i<retries; i++)); do
    if [[ -f "$file" ]] && grep -q "$pattern" "$file"; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

MODE="fg"
for arg in "$@"; do
  [[ "$arg" == "--daemon" ]] && MODE="daemon"
done

# Kill all child processes on exit (Ctrl+C) in foreground mode
cleanup() { echo "\n[stop] Stopping services"; pkill -P $$ || true; }
if [[ "$MODE" != "daemon" ]]; then
  trap cleanup EXIT INT TERM
fi

API_PORT="${API_PORT:-8000}"
WEB_PORT_ARG=""
for arg in "$@"; do
  if [[ "$arg" == --web-port=* ]]; then
    WEB_PORT_ARG="${arg#--web-port=}"
  fi
done

echo "[start] Launching API on http://127.0.0.1:${API_PORT} ($MODE)"
UVICORN_CMD=(uvicorn api.main:app --host 0.0.0.0 --port "${API_PORT}")

mkdir -p run

if [[ "$MODE" == "daemon" ]]; then
  nohup "${UVICORN_CMD[@]}" > logs/api.log 2>&1 &
  API_PID=$!
  echo $API_PID > run/api.pid
else
  "${UVICORN_CMD[@]}" > logs/api.log 2>&1 &
  API_PID=$!
  echo $API_PID > run/api.pid
fi

if wait_log logs/api.log "Application startup complete." 120 0.5; then
  echo "[ok] API is up (PID $API_PID)"
else
  echo "[warn] API readiness not confirmed by logs; continuing. Check logs/api.log"
fi

choose_web_port() {
  local explicit="${WEB_PORT_ARG:-${WEB_PORT:-}}"
  if [[ -n "$explicit" ]]; then
    echo "$explicit"; return 0
  fi
  # Offline-safe default without probing
  echo 5500
}

WEB_PORT="$(choose_web_port)"
export WEB_PORT
echo "[start] Launching static web (web/) on http://127.0.0.1:${WEB_PORT} ($MODE)"
if [[ "$MODE" == "daemon" ]]; then
  (cd web && nohup python -m http.server "$WEB_PORT" > "$ROOT_DIR/logs/web.log" 2>&1 & echo $! > "$ROOT_DIR/run/web.pid")
else
  (cd web && python -m http.server "$WEB_PORT" > ../logs/web.log 2>&1 & echo $! > ../run/web.pid)
fi
WEB_PID=$(cat run/web.pid 2>/dev/null || true)

# Verify web process exists instead of port probing
if [[ -n "${WEB_PID:-}" ]] && ps -p "$WEB_PID" > /dev/null 2>&1; then
  echo "[ok] Web is up (PID $WEB_PID)"
else
  echo "[warn] Static web server process not confirmed; check logs/web.log"
fi

echo "\n[ready] Access points:"
echo "  - API:  http://localhost:${API_PORT} (Docs: /docs)"
echo "  - Web:  http://localhost:${WEB_PORT}"
echo "\nLogs in ./logs/*.log"

if [[ "$MODE" == "daemon" ]]; then
  echo "[done] Services running in background (PIDs in ./run). Use scripts/stop.sh to stop."
else
  echo "\nUse Ctrl+C to stop."
  # Keep foreground alive while children run
  wait
fi
