#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$ROOT_DIR"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  echo "[error] docker compose/docker-compose não encontrado." >&2
  exit 1
fi

COMPOSE_FILE="docker-compose.yml"
PURGE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prod)
      COMPOSE_FILE="docker-compose.prod.yml"
      shift ;;
    --purge)
      PURGE=1
      shift ;;
    *)
      echo "Uso: $0 [--prod] [--purge]"; exit 1 ;;
  esac
done

echo "[compose] Parando serviços ($COMPOSE_FILE)"
if [[ $PURGE -eq 1 ]]; then
  echo "[compose] Removendo volumes (-v)"
  "${DC[@]}" -f "$COMPOSE_FILE" down -v
else
  "${DC[@]}" -f "$COMPOSE_FILE" down
fi

echo "[done]"

