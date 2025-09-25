#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$ROOT_DIR"

# Detect docker compose command
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  echo "[error] docker compose/docker-compose não encontrado." >&2
  exit 1
fi

COMPOSE_FILE="docker-compose.yml"
REBUILD=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prod)
      COMPOSE_FILE="docker-compose.prod.yml"
      shift ;;
    --rebuild)
      REBUILD=1
      shift ;;
    *)
      echo "Uso: $0 [--prod] [--rebuild]"; exit 1 ;;
  esac
done

echo "[compose] Using $COMPOSE_FILE"

# Prepare environment
mkdir -p data logs
if [[ ! -f .env ]]; then
  echo "[compose] Criando .env a partir de .env.example"
  cp .env.example .env
fi

if [[ $REBUILD -eq 1 ]]; then
  echo "[compose] Rebuild de imagens (--no-cache)"
  "${DC[@]}" -f "$COMPOSE_FILE" build --no-cache
fi

echo "[compose] Subindo serviços em segundo plano"
"${DC[@]}" -f "$COMPOSE_FILE" up -d --build

# Wait for API to be reachable
wait_http() {
  local url="$1" retries="${2:-60}" delay="${3:-1}"
  python - "$url" "$retries" "$delay" <<'PY'
import sys, time, urllib.request
url, retries, delay = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
for _ in range(retries):
    try:
        with urllib.request.urlopen(url, timeout=1) as r:
            if 200 <= r.status < 500:
                sys.exit(0)
    except Exception:
        time.sleep(delay)
print('timeout', file=sys.stderr)
sys.exit(1)
PY
}

echo "[compose] Aguardando API em http://localhost:8000/docs"
if wait_http "http://localhost:8000/docs" 120 1; then
  echo "[ok] API disponível."
else
  echo "[warn] API não respondeu a tempo; verifique logs: ${DC[*]} -f $COMPOSE_FILE logs"
fi

echo "\n[ready] Endpoints:"
echo "  - API:  http://localhost:8000 (Docs: /docs)"
echo "  - Painel (estático local): abra web/index.html (API http://localhost:8000)"
echo "\nDerrubar: scripts/stop-compose.sh${COMPOSE_FILE/docker-compose.yml/}"

