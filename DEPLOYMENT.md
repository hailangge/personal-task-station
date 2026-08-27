# Personal Task Station Deployment Guide

This project is production-ready for **personal or small-team operation** when it is run behind a trusted network boundary. The primary launch path is a host-based service on Linux. Docker Compose is kept as an alternate packaging path.

## Recommended Access Plan

- **Local only:** bind `PTS_HOST=127.0.0.1`, `PTS_PORT=8000`, then use `http://127.0.0.1:8000` with `X-API-Key`.
- **LAN or private VPN:** bind `PTS_HOST=0.0.0.0` or a specific LAN IP and connect to `http://<server-lan-ip>:8000` with `X-API-Key`; restrict access with firewall/VPN rules.
- **Public internet:** do not expose the app port directly. Put Caddy, nginx, Tailscale Funnel, Cloudflare Tunnel, or another hardened reverse proxy/tunnel in front and terminate HTTPS there.
- **Direct HTTPS/mTLS:** optional. Set `PTS_SSL_CERTFILE` and `PTS_SSL_KEYFILE`; set `PTS_SSL_CAFILE` only when clients must present mTLS certificates.

The server requires an API key for all application APIs except `/health`. The desktop client intentionally blocks plain HTTP unless explicit local/private-network HTTP is enabled for loopback, RFC1918 LAN, link-local, or `.local` hosts.

## 1. Host-Based Service (Primary)

### 1.1 Prepare Environment

```bash
cp .env.example .env.host
$EDITOR .env.host
```

Minimum `.env.host` values:

```bash
PTS_API_KEY=replace-with-openssl-rand-hex-32
PTS_HOST=127.0.0.1
PTS_PORT=8000
PTS_DATA_DIR=/home/pts/personal-task-station/.local/pts-data
PTS_DATABASE_URL=sqlite:////home/pts/personal-task-station/.local/pts-data/personal_task_station.sqlite3
```

For LAN access, use one of:

```bash
PTS_HOST=0.0.0.0
# or a specific interface address, for example:
PTS_HOST=192.168.1.20
```

### 1.1b Optional: Automated Bill Ingestion

Append to `.env.host` to monitor a bill mailbox (e.g. `2924799749@qq.com`):

```bash
PTS_IMAP_HOST=imap.qq.com
PTS_IMAP_PORT=993
PTS_IMAP_USERNAME=2924799749@qq.com
PTS_IMAP_PASSWORD=the-imap-authorization-code-not-the-login-password
PTS_EMAIL_POLL_SECONDS=300
PTS_WECHAT_BILL_ZIP_PASSWORD=password-inside-each-bill-email-sms
PTS_ALIPAY_BILL_ZIP_PASSWORD=your-alipay-zip-password
```

Startup seeds this mailbox as an account automatically, and the background poller ingests only bill-related emails (encrypted WeChat/Alipay bill zips, invoice PDFs) into the ledger with external-id idempotency. SMS webhook and screenshot endpoints are documented in the README ("Automated bill ingestion"). Install the parsing extras once: `.venv/bin/pip install 'personal-task-station[email]'`.

### 1.2 Dry Run

```bash
scripts/run-host-server.sh --dry-run
```

### 1.3 Start Server

```bash
scripts/run-host-server.sh --env-file .env.host
```

The script is idempotent. It creates the data directory, creates `.env.host` when missing, installs server dependencies into `.venv` when needed, runs Alembic migrations when available, and starts `pts-server`.

### 1.4 Smoke Test

In another terminal:

```bash
source .env.host
scripts/smoke-test.sh --base-url "http://127.0.0.1:${PTS_PORT}" --api-key "$PTS_API_KEY"
```

Useful manual checks:

```bash
curl http://127.0.0.1:8000/health
curl -H "X-API-Key: $PTS_API_KEY" http://127.0.0.1:8000/tasks
curl -H "X-API-Key: $PTS_API_KEY" -H "Content-Type: application/json" \
  -d '{"title":"Alias check","scheduled_date":"2026-01-01","start_time":"2026-01-01T09:00:00","due_time":"2026-01-01T10:00:00","notes":"Public names","priority":"high"}' \
  http://127.0.0.1:8000/tasks
```

Task create/update payloads accept `scheduled_date`/`task_date`, `start_time`/`start_at`, `due_time`/`due_at`, and `notes`/`note`. Responses include both names, while `priority` is normalized to integer `1`-`5` even when requests send labels such as `high` or numeric strings such as `"5"`.

For LAN access from another device:

```bash
curl -H "X-API-Key: $PTS_API_KEY" http://<server-lan-ip>:8000/health
curl -H "X-API-Key: $PTS_API_KEY" http://<server-lan-ip>:8000/tasks
```

## 2. systemd User Service

Install the template after the host service has been prepared:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/personal-task-station.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now personal-task-station.service
systemctl --user status personal-task-station.service
```

The template assumes this checkout lives at `~/personal-task-station`, uses `~/personal-task-station/.env.host`, and runs `~/personal-task-station/.venv/bin/pts-server`. Edit those paths if your deployment directory differs.

To start the service on login-less servers:

```bash
loginctl enable-linger "$USER"
```

## 3. Docker Compose (Alternate)

Docker Compose is useful when an operator wants container isolation. It is not the primary recommendation for this small SQLite-backed service.

```bash
cp .env.example .env
$EDITOR .env
scripts/deploy-linux-server.sh --dry-run
scripts/deploy-linux-server.sh --api-key "$PTS_API_KEY" --port 8000
scripts/smoke-test.sh --base-url http://127.0.0.1:8000 --api-key "$PTS_API_KEY"
```

The Compose service stores SQLite data under `PTS_DATA_DIR` and publishes `PTS_PORT` on the host. The container listens on `0.0.0.0:8000` internally.

## 4. Desktop Client Connection

Install and launch locally:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[client]"
pts-client
```

Connection settings:

| Scenario | Server URL | Required options |
| --- | --- | --- |
| Same machine | `http://127.0.0.1:8000` | Enable “Allow local HTTP for development” |
| LAN/VPN via direct HTTP | `http://<server-lan-ip>:8000` | API key; enable “Allow HTTP for localhost/private LAN” |
| HTTPS proxy/tunnel | `https://<proxy-host>` | API key; custom CA path if self-signed |
| Direct server HTTPS | `https://<server-host>:8443` | API key; `PTS_SERVER_CERT_PATH` if self-signed |
| Direct mTLS | `https://<server-host>:8443` | API key, server CA, client certificate, client key |

Environment variables for client/skill wrappers:

```bash
export PTS_SKILL_BASE_URL="https://<proxy-or-server>"
export PTS_SKILL_API_KEY="<api-key>"
export PTS_SERVER_CERT_PATH="$HOME/.pts/certs/ca-cert.pem"       # optional self-signed CA
export PTS_CLIENT_CERT_PATH="$HOME/.pts/certs/client-cert.pem"   # optional mTLS
export PTS_CLIENT_KEY_PATH="$HOME/.pts/certs/client-key.pem"     # optional mTLS
```

## 5. HTTPS and mTLS

Generate development/self-managed certificates:

```bash
python scripts/generate_certs.py --output-dir certs --hostname <server-host>
```

Set direct TLS on the server:

```bash
PTS_SSL_CERTFILE=/absolute/path/to/certs/server-cert.pem
PTS_SSL_KEYFILE=/absolute/path/to/certs/server-key.pem
```

Set mTLS only when required:

```bash
PTS_SSL_CAFILE=/absolute/path/to/certs/ca-cert.pem
```

For most LAN/public usage, a reverse proxy or private tunnel is simpler and safer than exposing Uvicorn directly.

## 6. Operator Checklist

- Use a unique random API key, preferably `openssl rand -hex 32`.
- Keep SQLite data in `PTS_DATA_DIR` and back it up regularly.
- Keep `.env.host`, `.env`, private keys, and database files out of Git.
- Bind to `127.0.0.1` unless LAN/VPN access is explicitly needed.
- Restrict LAN ports with host firewall rules.
- Use a reverse proxy/tunnel with HTTPS for access outside the local machine.
- Run `scripts/smoke-test.sh` after deploys and restarts.
