#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/smoke-test.sh [--base-url URL] [--api-key KEY] [--timeout SECONDS] [--cacert FILE] [--cert FILE --key FILE] [--dry-run]

Runs a minimal operator smoke test against a running Personal Task Station
server: public health, authenticated task list, create task, fetch task, delete
task. Safe to repeat; the temporary task is deleted before exit.
USAGE
}

BASE_URL="${PTS_SMOKE_BASE_URL:-${PTS_SKILL_BASE_URL:-http://127.0.0.1:8000}}"
API_KEY="${PTS_SMOKE_API_KEY:-${PTS_API_KEY:-${PTS_SKILL_API_KEY:-}}}"
TIMEOUT="${PTS_SMOKE_TIMEOUT:-10}"
CACERT="${PTS_SERVER_CERT_PATH:-}"
CERT="${PTS_CLIENT_CERT_PATH:-}"
KEY="${PTS_CLIENT_KEY_PATH:-}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url) BASE_URL="$2"; shift 2 ;;
    --api-key) API_KEY="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --cacert) CACERT="$2"; shift 2 ;;
    --cert) CERT="$2"; shift 2 ;;
    --key) KEY="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

BASE_URL="${BASE_URL%/}"
CURL_TLS=()
if [[ -n "$CACERT" ]]; then
  CURL_TLS+=(--cacert "$CACERT")
fi
if [[ -n "$CERT" ]]; then
  CURL_TLS+=(--cert "$CERT")
fi
if [[ -n "$KEY" ]]; then
  CURL_TLS+=(--key "$KEY")
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] base url: $BASE_URL"
  echo "[dry-run] timeout: $TIMEOUT"
  echo "[dry-run] would call /health, /tasks, create/get/delete one smoke task"
  exit 0
fi

if [[ -z "$API_KEY" ]]; then
  echo "API key is required via --api-key, PTS_API_KEY, or PTS_SMOKE_API_KEY." >&2
  exit 2
fi

command -v curl >/dev/null 2>&1 || { echo "curl is required." >&2; exit 1; }
command -v python >/dev/null 2>&1 || { echo "python is required." >&2; exit 1; }

tmp_create="$(mktemp)"
tmp_get="$(mktemp)"
cleanup() {
  rm -f "$tmp_create" "$tmp_get"
}
trap cleanup EXIT

echo "[smoke] GET /health"
curl -fsS --max-time "$TIMEOUT" "${CURL_TLS[@]}" "$BASE_URL/health" >/dev/null

echo "[smoke] GET /tasks"
curl -fsS --max-time "$TIMEOUT" "${CURL_TLS[@]}" -H "X-API-Key: $API_KEY" "$BASE_URL/tasks" >/dev/null

echo "[smoke] POST /tasks"
curl -fsS --max-time "$TIMEOUT" "${CURL_TLS[@]}" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title":"PTS smoke test task","description":"created by scripts/smoke-test.sh","scheduled_date":"2026-01-01","priority":"medium"}' \
  "$BASE_URL/tasks" > "$tmp_create"

task_id="$(python - <<'PY' "$tmp_create"
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["id"])
PY
)"

if [[ -z "$task_id" ]]; then
  echo "Could not parse created task id." >&2
  exit 1
fi

echo "[smoke] GET /tasks/$task_id"
curl -fsS --max-time "$TIMEOUT" "${CURL_TLS[@]}" -H "X-API-Key: $API_KEY" "$BASE_URL/tasks/$task_id" > "$tmp_get"
python - <<'PY' "$tmp_get"
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
assert payload["title"] == "PTS smoke test task"
PY

echo "[smoke] DELETE /tasks/$task_id"
curl -fsS --max-time "$TIMEOUT" "${CURL_TLS[@]}" -X DELETE -H "X-API-Key: $API_KEY" "$BASE_URL/tasks/$task_id" >/dev/null

echo "[smoke] ok"
