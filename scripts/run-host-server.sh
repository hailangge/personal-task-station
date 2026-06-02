#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/run-host-server.sh [--env-file FILE] [--host HOST] [--port PORT] [--data-dir DIR] [--api-key KEY] [--dry-run]

Starts Personal Task Station directly on the host as the primary recommended
single-machine/LAN service mode. The script is idempotent: it creates the data
folder and an env file when missing, preserves an existing env file, installs
server dependencies into .venv when needed, runs Alembic migrations when
available, then starts pts-server.
USAGE
}

ENV_FILE="${PTS_ENV_FILE:-.env.host}"
HOST="${PTS_HOST:-127.0.0.1}"
PORT="${PTS_PORT:-8000}"
DATA_DIR="${PTS_DATA_DIR:-$PWD/.local/pts-data}"
API_KEY="${PTS_API_KEY:-}"
DRY_RUN=0
INSTALL_DEPS=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --data-dir) DATA_DIR="$2"; shift 2 ;;
    --api-key) API_KEY="$2"; shift 2 ;;
    --no-install) INSTALL_DEPS=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ -z "$API_KEY" ]]; then
  if [[ -f "$ENV_FILE" ]]; then
    API_KEY="$(grep -E '^PTS_API_KEY=' "$ENV_FILE" | tail -n1 | cut -d= -f2- || true)"
  fi
  if [[ -z "$API_KEY" ]]; then
    if command -v openssl >/dev/null 2>&1; then
      API_KEY="$(openssl rand -hex 32)"
    else
      API_KEY="change-me-$(date +%s)"
    fi
  fi
fi

DATABASE_URL="sqlite:///${DATA_DIR%/}/personal_task_station.sqlite3"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] repo: $repo_root"
  echo "[dry-run] env file: $ENV_FILE"
  echo "[dry-run] data dir: $DATA_DIR"
  echo "[dry-run] bind: $HOST:$PORT"
  echo "[dry-run] would create env/data, install server deps if needed, migrate, then run pts-server"
  exit 0
fi

mkdir -p "$DATA_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<ENV
PTS_API_KEY=$API_KEY
PTS_HOST=$HOST
PTS_PORT=$PORT
PTS_DATA_DIR=$DATA_DIR
PTS_DATABASE_URL=$DATABASE_URL
ENV
  chmod 600 "$ENV_FILE"
  echo "Created $ENV_FILE"
else
  echo "Using existing $ENV_FILE"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export PTS_DATA_DIR="${PTS_DATA_DIR:-$DATA_DIR}"
export PTS_DATABASE_URL="${PTS_DATABASE_URL:-$DATABASE_URL}"
export PTS_HOST="${PTS_HOST:-$HOST}"
export PTS_PORT="${PTS_PORT:-$PORT}"
export PTS_API_KEY="${PTS_API_KEY:-$API_KEY}"

mkdir -p "$PTS_DATA_DIR"

if [[ ! -x .venv/bin/pts-server ]]; then
  if [[ "$INSTALL_DEPS" -eq 0 ]]; then
    echo ".venv/bin/pts-server is missing. Re-run without --no-install or install the project first." >&2
    exit 1
  fi
  python -m venv .venv
  .venv/bin/python -m pip install -U pip
  .venv/bin/python -m pip install -e ".[server]"
fi

if [[ -x .venv/bin/alembic ]]; then
  .venv/bin/alembic upgrade head
fi

scheme="http"
if [[ -n "${PTS_SSL_CERTFILE:-}" && -n "${PTS_SSL_KEYFILE:-}" ]]; then
  scheme="https"
fi

echo "Starting Personal Task Station on ${scheme}://${PTS_HOST}:${PTS_PORT}"
echo "Smoke test: scripts/smoke-test.sh --base-url ${scheme}://${PTS_HOST}:${PTS_PORT} --api-key '<redacted>'"
exec .venv/bin/pts-server
