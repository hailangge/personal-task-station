# Personal Task Station MVP

`personal-task-station` is a single-repo MVP that implements:

- A Linux-deployable FastAPI server with SQLite persistence and API-key protected access
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
scripts/run-host-server.sh
scripts/smoke-test.sh
certs/
deploy/systemd/
fixtures/
src/personal_task_station/
tests/
```

Key packages:

- `src/personal_task_station/server/`: FastAPI app, routers, and service logic
- `src/personal_task_station/client/`: PySide6 desktop client
- `src/personal_task_station/shared/`: shared enums, schemas, settings, and ORM models
- `src/personal_task_station/skills/`: agent-facing wrappers and CLIs
- `scripts/run-host-server.sh`: primary host-based server startup helper
- `scripts/smoke-test.sh`: repeatable health/API smoke test helper
- `scripts/deploy-linux-server.sh`: alternate Docker Compose server deployment helper
- `deploy/systemd/personal-task-station.service`: systemd user service template
- `scripts/generate_certs.py`: self-signed CA / server / client certificate generator
- `scripts/validate_security.py`: end-to-end security validation script
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

## Access model

The recommended launch path is a host-based service bound to `127.0.0.1` for same-machine use, or a private LAN/VPN address when remote access is needed. All application APIs require `X-API-Key`; `/health` is public for operators and container health checks.

Do **not** expose the app port directly to the public internet. Use a reverse proxy or private tunnel such as Caddy, nginx, Tailscale, or Cloudflare Tunnel for public/remote HTTPS. Direct server HTTPS and mTLS are optional when you prefer the app server to terminate TLS itself.

## Generate certificates (optional HTTPS / mTLS)

Generate self-signed certificates when using direct HTTPS/mTLS:

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

- The desktop client rejects HTTP unless explicit local/private-network HTTP is enabled. Use it only for `localhost`, loopback, RFC1918 LAN, link-local, or `.local` hosts.
- Provide `PTS_SERVER_CERT_PATH` so clients can verify a self-signed server certificate.
- When `PTS_SSL_CAFILE` is set, the server enforces mTLS and rejects clients without a valid certificate.
- Production-like deployments should use a long random API key and a private network, reverse proxy, or tunnel boundary.

## Host server deployment (recommended)

```bash
cp .env.example .env.host
scripts/run-host-server.sh --dry-run
scripts/run-host-server.sh --env-file .env.host
```

Smoke test from another terminal:

```bash
source .env.host
scripts/smoke-test.sh --base-url "http://127.0.0.1:${PTS_PORT}" --api-key "$PTS_API_KEY"
```

Local address: `http://127.0.0.1:8000`. For LAN/private VPN, set `PTS_HOST=0.0.0.0` or the server LAN IP and connect to `http://<server-lan-ip>:8000` with the same API key. In the desktop client, enable “Allow HTTP for localhost/private LAN” for this explicit private-network HTTP mode.

## Docker server deployment (alternate)

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

Task payloads accept both public/spec field names and internal legacy names: `scheduled_date`/`task_date`, `start_time`/`start_at`, `due_time`/`due_at`, and `notes`/`note`. Responses include both names for compatibility, and `priority` is always returned as an integer from 1 to 5. Create/update requests may send priority as an integer, a numeric string, or one of `critical`, `high`, `medium`, `normal`, `low`, or `lowest`.

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
- Finance CSV import, month summary, transaction list, duplicate review/undo, and reanalyze controls
- Connection configuration with API key and certificate path fields

## Automated bill ingestion

Beyond manual CSV import, the server can ingest transactions automatically:

1. **Bill mailbox monitoring (P0).** Point `PTS_IMAP_*` variables at a mailbox (e.g. `2924799749@qq.com` via `imap.qq.com:993` with an IMAP auth code) and set `PTS_EMAIL_POLL_SECONDS` to enable a background poller. The account is seeded automatically at startup. Only **bill-related** emails are processed (`PTS_EMAIL_BILL_ONLY=1`, default): subject keywords such as 账单 / 流水证明 / 发票, or finance senders carrying zip/pdf attachments.
   - Encrypted WeChat Pay / Alipay monthly bill zips are opened with `PTS_WECHAT_BILL_ZIP_PASSWORD` / `PTS_ALIPAY_BILL_ZIP_PASSWORD` (or comma-separated `PTS_BILL_ZIP_PASSWORDS`) and their official CSVs parsed into transactions (idempotent via transaction ids).
   - Electronic invoice PDF attachments (京东/天猫 deliver these by email) are parsed with pdfplumber; the invoice number becomes the dedupe id.
2. **Webhook for bank SMS forwarding (P1).** Configure [SmsForwarder](https://github.com/pppscn/SmsForwarder) on an Android phone to POST dynamic-account SMS texts:

   ```bash
   curl -sk -X POST "http://127.0.0.1:8000/ingest/webhook" \
     -H "X-API-Key: $PTS_API_KEY" -H "Content-Type: application/json" \
     -d '{"text":"【招商银行】您尾号1234的账户7月1日12:00完成快捷支付交易人民币100.00元","source_name":"cmb_sms"}'
   ```

   Plain-text bodies work too. Re-delivering the same message reports `skipped_duplicate`.
3. **Screenshot ingestion (P2, confirm-first).** Upload payment screenshots; when LiteLLM vision is configured they are pre-filled automatically, otherwise you supply fields manually and confirm:

   ```bash
   curl -sk -X POST "http://127.0.0.1:8000/ingest/screenshots" \
     -H "X-API-Key: $PTS_API_KEY" -F file=@shot.png
   # -> {"id": 7, "status": "proposed", ...}
   curl -sk -X POST "http://127.0.0.1:8000/ingest/screenshots/7/confirm" \
     -H "X-API-Key: $PTS_API_KEY" -H "Content-Type: application/json" \
     -d '{"occurred_on":"2026-08-01","amount":"66.50","merchant_name":"全家便利店"}'
   ```

Manual sync without the background poller: `POST /email-import/sync?force=true` (per-account import keeps its own endpoint under `/email-import/accounts/{id}/import`, returning `409` when nothing new was ingested).

See `.env.example` for every variable involved. See `research/information-acquisition-2026-08.md` for the full channel analysis.

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

The finance MVP is CSV-first: manually import transaction exports, then review normalized transactions, monthly summaries, duplicate groups, and undo any incorrect duplicate merge. External bank/email automation is optional/experimental and is not required for the reliable MVP path.

From the desktop client, open the **Finance** tab, choose the month, set a source name such as `fixture`, click **Import CSV**, select a CSV file, then use **Load summary**, **Reanalyze**, or **Undo selected duplicate** as needed.

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
