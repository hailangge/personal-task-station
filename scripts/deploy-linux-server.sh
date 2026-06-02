#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/deploy-linux-server.sh [--env-file FILE] [--data-dir DIR] [--api-key KEY] [--port PORT] [--dry-run]

Builds and starts the Docker Compose server deployment. The script is idempotent:
it creates an env file when missing, preserves an existing env file, ensures the
data directory exists, builds the image, starts the service, and prints smoke
test commands.
USAGE
}

ENV_FILE="${PTS_COMPOSE_ENV_FILE:-.env}"
DATA_DIR="${PTS_DATA_DIR:-$PWD/.local/docker-data}"
API_KEY="${PTS_API_KEY:-}"
PORT="${PTS_PORT:-8000}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --data-dir) DATA_DIR="$2"; shift 2 ;;
    --api-key) API_KEY="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$API_KEY" ]]; then
  if [[ -f "$ENV_FILE" ]]; then
    API_KEY="$(grep -E '^PTS_API_KEY=' "$ENV_FILE" | tail -n1 | cut -d= -f2- || true)"
  fi
fi

if [[ -z "$API_KEY" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    API_KEY="$(openssl rand -hex 32)"
  else
    API_KEY="change-me-$(date +%s)"
  fi
fi

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    echo "Docker Compose is required." >&2
    exit 1
  fi
}

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] env file: $ENV_FILE"
  echo "[dry-run] data dir: $DATA_DIR"
  echo "[dry-run] port: $PORT"
  echo "[dry-run] would create env/data when needed and run: docker compose up -d --build server"
  exit 0
fi

command -v docker >/dev/null 2>&1 || { echo "docker is required." >&2; exit 1; }
mkdir -p "$DATA_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
cat > "$ENV_FILE" <<ENV
PTS_API_KEY=$API_KEY
PTS_PORT=$PORT
PTS_DATA_DIR=$DATA_DIR
ENV
  chmod 600 "$ENV_FILE"
  echo "Created $ENV_FILE"
else
  echo "Using existing $ENV_FILE"
fi

echo "Starting Personal Task Station server on port $PORT..."
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
compose_cmd up -d --build server

echo "Health check: curl http://127.0.0.1:$PORT/health"
echo "Smoke test: scripts/smoke-test.sh --base-url http://127.0.0.1:$PORT --api-key '<redacted>'"
