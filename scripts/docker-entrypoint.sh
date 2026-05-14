#!/bin/sh
set -e

# Default data dir
DATA_DIR="${PTS_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"

# Default database URL points to the mounted data volume
export PTS_DATABASE_URL="${PTS_DATABASE_URL:-sqlite:///${DATA_DIR}/personal_task_station.sqlite3}"

# Run Alembic migrations (idempotent)
echo "[entrypoint] Running database migrations..."
alembic upgrade head

UVICORN_ARGS=""
if [ -n "${PTS_SSL_CERTFILE:-}" ] && [ -n "${PTS_SSL_KEYFILE:-}" ]; then
  UVICORN_ARGS="$UVICORN_ARGS --ssl-certfile ${PTS_SSL_CERTFILE} --ssl-keyfile ${PTS_SSL_KEYFILE}"
  if [ -n "${PTS_SSL_CAFILE:-}" ]; then
    UVICORN_ARGS="$UVICORN_ARGS --ssl-ca-certs ${PTS_SSL_CAFILE} --ssl-cert-reqs 2"
  fi
fi

echo "[entrypoint] Starting server on ${PTS_HOST:-0.0.0.0}:${PTS_PORT:-8000}..."
exec uvicorn personal_task_station.server.app:app \
    --host "${PTS_HOST:-0.0.0.0}" \
    --port "${PTS_PORT:-8000}" \
    --workers "${PTS_WORKERS:-1}" \
    --app-dir src \
    $UVICORN_ARGS
