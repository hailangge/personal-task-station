# Personal Task Station MVP

`personal-task-station` is a single-repo MVP that implements:

- A Linux-deployable FastAPI server with SQLite persistence
- Task CRUD, subitems, status history, and calendar aggregation APIs
- Billing CSV import, normalization, dedupe/merge, fallback categorization, and monthly summaries
- A Windows/Linux PySide6 desktop client with task filters/actions, calendar styles, date popups, finance views, and connection config
- Agent-facing task and finance skill wrappers
- Unit, integration, and offscreen UI tests

## Repository layout

```text
pyproject.toml
README.md
DEPLOYMENT.md
specification/requirements.md
specification/design.md
specification/tasks.md
Dockerfile
docker-compose.yml
scripts/generate_certs.py
scripts/validate_security.py
certs/
fixtures/
src/personal_task_station/
tests/
```

Key packages:

- `src/personal_task_station/server/`: FastAPI app, routers, and service logic
- `src/personal_task_station/client/`: PySide6 desktop client
- `src/personal_task_station/shared/`: shared enums, schemas, settings, and ORM models
- `src/personal_task_station/skills/`: agent-facing wrappers and CLIs
- `scripts/generate_certs.py`: self-signed CA / server / client certificate generator
- `scripts/validate_security.py`: end-to-end security validation script
- `scripts/deploy-linux-server.sh`: repeatable Docker Compose server deployment helper
- `scripts/package-linux-client.sh`: Linux PyInstaller client package helper with source fallback
- `scripts/package-windows-client.ps1`: Windows PyInstaller client package helper

For production deployment instructions, see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

## Setup

Create a local environment and install the project:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Generate certificates (HTTPS / mTLS)

The server **requires HTTPS** in production. Generate self-signed certificates:

```bash
.venv/bin/python scripts/generate_certs.py --output-dir certs --hostname localhost
```

Output files:

- `certs/ca-cert.pem` — distribute to clients for server verification
- `certs/ca-key.pem` — keep secret (CA signing key)
- `certs/server-cert.pem` + `certs/server-key.pem` — server HTTPS identity
- `certs/client-cert.pem` + `certs/client-key.pem` — optional, for mTLS client authentication

## Configuration

Server and skill settings are driven by environment variables:

```bash
export PTS_API_KEY="change-me"
export PTS_DATABASE_URL="sqlite:///$PWD/.local/personal_task_station.sqlite3"
export PTS_HOST="127.0.0.1"
export PTS_PORT="8000"
```

Enable HTTPS (recommended):

```bash
export PTS_SSL_CERTFILE="$PWD/certs/server-cert.pem"
export PTS_SSL_KEYFILE="$PWD/certs/server-key.pem"
```

Enable mTLS (optional — server verifies client certificates):

```bash
export PTS_SSL_CAFILE="$PWD/certs/ca-cert.pem"
```

Client / skill trust configuration:

```bash
export PTS_SERVER_CERT_PATH="$PWD/certs/ca-cert.pem"
export PTS_CLIENT_CERT_PATH="$PWD/certs/client-cert.pem"
export PTS_CLIENT_KEY_PATH="$PWD/certs/client-key.pem"
```

Optional LiteLLM integration:

```bash
export PTS_LITELLM_BASE_URL="https://your-litellm-endpoint"
export PTS_LITELLM_MODEL="gpt-5.4"
export PTS_LITELLM_API_KEY="..."
```

Security notes:

- **HTTP is rejected except explicit localhost development.** Enable “Allow local HTTP for development” only for `localhost`/`127.0.0.1`.
- Provide `PTS_SERVER_CERT_PATH` so clients can verify a self-signed server certificate.
- When `PTS_SSL_CAFILE` is set, the server enforces mTLS and rejects clients without a valid certificate.
- The desktop client and skill wrappers do not silently ignore TLS errors.
- Production deployments should use HTTPS and a long random API key.

## Docker server deployment

For a local Linux Docker/Compose deployment:

```bash
scripts/deploy-linux-server.sh --api-key "change-this-long-random-token" --port 8000
curl -H "X-API-Key: change-this-long-random-token" http://127.0.0.1:8000/health
```

The compose service reads `PTS_API_KEY`, `PTS_PORT`, `PTS_DATA_DIR`, and optional TLS paths from `.env`.

## Run the server

```bash
.venv/bin/pts-server
```

The server exposes:

- `GET /health`
- `GET/POST/PATCH/DELETE /tasks`
- `POST /tasks/{id}/status`
- `POST /tasks/{id}/subitems`
- `PATCH/DELETE /tasks/{id}/subitems/{subitem_id}`
- `POST /tasks/{id}/subitems/{subitem_id}/toggle`
- `POST /tasks/{id}/subitems/reorder`
- `GET /tasks/{id}/history`
- `GET /tasks/calendar/summary`
- `GET /tasks/calendar/month`
- `POST /billing/import`
- `GET /billing/transactions`
- `GET /billing/summary/monthly`
- `GET /billing/duplicates`
- `POST /billing/merged/{id}/undo`
- `POST /billing/reanalyze`

All protected endpoints require `X-API-Key`.

## Run the desktop client

The client stores configuration in `.local/client_settings.json` by default.

```bash
.venv/bin/pts-client
```

Client capabilities in this MVP:

- Month, week, and compact calendar modes
- Calendar day markers based on aggregated task status
- Task list filters for all/today/this week/this month, status, and keyword
- Task create/edit/delete, status changes, subitem add/delete/toggle, and status history display
- Adjustable opacity and always-on-top behavior
- Date popup for daily tasks with quick add/edit/status switching
- Finance summary and transaction list views
- Connection configuration with API key and certificate path fields

## Package desktop clients

```bash
scripts/package-linux-client.sh --dry-run
scripts/package-linux-client.sh --output-dir dist/linux-client
```

On Windows PowerShell, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package-windows-client.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File scripts\package-windows-client.ps1 -OutputDir dist\windows-client
```

Windows packaging must run on a Windows host or CI runner so PyInstaller can create `pts-client.exe`.

## Import sample billing data

Fixture file:

- `fixtures/sample_transactions.csv`

Example using the finance skill wrapper:

```bash
PTS_SKILL_BASE_URL="https://127.0.0.1:8000" \
PTS_SKILL_API_KEY="$PTS_API_KEY" \
PTS_SKILL_SERVER_CERT_PATH="$PWD/certs/ca-cert.pem" \
.venv/bin/pts-finance-skill import \
  --source-name fixture \
  --file-path fixtures/sample_transactions.csv
```

Then inspect the summary:

```bash
PTS_SKILL_BASE_URL="https://127.0.0.1:8000" \
PTS_SKILL_API_KEY="$PTS_API_KEY" \
PTS_SKILL_SERVER_CERT_PATH="$PWD/certs/ca-cert.pem" \
.venv/bin/pts-finance-skill summary \
  --year 2026 \
  --month 3
```

## Run tests

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest
```

The UI tests use Qt offscreen mode so they can run on headless Linux.

## Local validation commands used for this MVP

The following commands were used during implementation:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python - <<'PY'
from personal_task_station.server.app import create_app
app = create_app('sqlite:///:memory:')
print(app.title)
PY
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
from PySide6.QtWidgets import QApplication
from personal_task_station.client.widgets.calendar_widget import TaskCalendarWidget
app = QApplication([])
widget = TaskCalendarWidget()
print(widget.mode_selector.currentText())
PY
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
```

## Known MVP boundaries

- The desktop client is implemented and smoke-tested offscreen on Linux; Windows behavior is designed for the same PySide6 codepath but was not executed on this machine.
- TLS certificate validation plumbing is implemented in the client and skills, but end-to-end HTTPS certificate deployment must be supplied by the runtime environment.
- The billing import pipeline currently targets CSV/TSV-like exports with alias-based normalization. New providers can be added by extending the field alias and normalization rules.
