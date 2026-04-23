# Personal Task Station — Deployment Guide

## 1. Overview

This guide covers the secure deployment of the Personal Task Station server and desktop client on Linux. By default, **all communication is encrypted via HTTPS**. Optional mutual TLS (mTLS) can be enabled to restrict connections to hosts possessing a valid client certificate.

## 2. Prerequisites

- Linux server (Ubuntu 22.04+, Debian 12+, or equivalent)
- Python 3.12+
- `openssl` CLI tool (for certificate inspection and debugging)
- `curl` (for connection testing)
- Firewall access to the configured server port (default 8000)

## 3. Install the Application

```bash
# Clone or copy the repository to the server
cd /opt/personal-task-station
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## 4. Certificate Generation

### 4.1 Understanding the Certificate Architecture

| File | Purpose | Distribution |
|------|---------|-------------|
| `ca-cert.pem` | Trust anchor for verifying server (and optionally client) certificates | **Deploy to every client** |
| `ca-key.pem` | CA private key for signing new certificates | **Server only, keep secret** |
| `server-cert.pem` + `server-key.pem` | Server's HTTPS identity | **Server only** |
| `client-cert.pem` + `client-key.pem` | Client identity for mTLS | **Authorized clients only** |

### 4.2 Generate Certificates

```bash
.venv/bin/python scripts/generate_certs.py \
  --output-dir /etc/pts/certs \
  --hostname your-server-hostname \
  --client-name pts-client
```

Set appropriate permissions:

```bash
sudo chown -R pts:pts /etc/pts/certs
sudo chmod 600 /etc/pts/certs/*-key.pem
sudo chmod 644 /etc/pts/certs/*.pem
```

> **Security Note**: Never commit private keys (`*-key.pem`) to version control. The repository `.gitignore` already excludes `certs/`.

### 4.3 Verify Certificate Chain

```bash
openssl verify -CAfile /etc/pts/certs/ca-cert.pem /etc/pts/certs/server-cert.pem
openssl verify -CAfile /etc/pts/certs/ca-cert.pem /etc/pts/certs/client-cert.pem
```

## 5. Server Deployment

### 5.1 Environment Variables

Create `/etc/pts/server.env`:

```bash
# Required
export PTS_API_KEY="change-this-to-a-long-random-string-min-32-chars"
export PTS_DATABASE_URL="sqlite:///var/lib/pts/personal_task_station.sqlite3"
export PTS_HOST="0.0.0.0"
export PTS_PORT="8443"

# HTTPS (required for production)
export PTS_SSL_CERTFILE="/etc/pts/certs/server-cert.pem"
export PTS_SSL_KEYFILE="/etc/pts/certs/server-key.pem"

# Optional: mTLS — when set, only clients with valid client certs can connect
export PTS_SSL_CAFILE="/etc/pts/certs/ca-cert.pem"

# Optional: LiteLLM integration
# export PTS_LITELLM_BASE_URL="https://your-litellm-endpoint"
# export PTS_LITELLM_MODEL="gpt-5.4"
# export PTS_LITELLM_API_KEY="..."
```

### 5.2 Create Directories and Database

```bash
sudo mkdir -p /var/lib/pts
sudo chown pts:pts /var/lib/pts
```

### 5.3 Systemd Service (Recommended)

Create `/etc/systemd/system/pts-server.service`:

```ini
[Unit]
Description=Personal Task Station Server
After=network.target

[Service]
Type=simple
User=pts
Group=pts
WorkingDirectory=/opt/personal-task-station
EnvironmentFile=/etc/pts/server.env
ExecStart=/opt/personal-task-station/.venv/bin/pts-server
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pts-server
sudo systemctl start pts-server
sudo systemctl status pts-server
```

View logs:

```bash
sudo journalctl -u pts-server -f
```

### 5.4 Verify Server is Running

```bash
# Without CA cert (should fail)
curl -v https://127.0.0.1:8443/health 2>&1 | grep -E "SSL|certificate"

# With CA cert (should succeed for /health)
curl --cacert /etc/pts/certs/ca-cert.pem https://127.0.0.1:8443/health

# With CA cert + API key (should succeed for protected endpoints)
curl --cacert /etc/pts/certs/ca-cert.pem \
  -H "X-API-Key: your-api-key" \
  https://127.0.0.1:8443/tasks

# mTLS: with client cert (if PTS_SSL_CAFILE is set)
curl --cacert /etc/pts/certs/ca-cert.pem \
  --cert /etc/pts/certs/client-cert.pem \
  --key /etc/pts/certs/client-key.pem \
  https://127.0.0.1:8443/health
```

## 6. Firewall Configuration

### 6.1 UFW (Ubuntu/Debian)

```bash
# Deny HTTP port (if previously open)
sudo ufw deny 8000/tcp

# Allow HTTPS port only
sudo ufw allow 8443/tcp

# Restrict to specific IP range (recommended)
sudo ufw allow from 192.168.1.0/24 to any port 8443 proto tcp
```

### 6.2 iptables

```bash
sudo iptables -A INPUT -p tcp --dport 8443 -s 192.168.1.0/24 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8443 -j DROP
sudo iptables -A INPUT -p tcp --dport 8000 -j DROP
```

### 6.3 Cloud Provider Security Groups

- Open inbound TCP on port 8443
- Restrict source to your office/VPN IP range
- Do **not** open port 8000 (HTTP)

## 7. Client Deployment

### 7.1 Desktop Client Setup

Install the application on the client machine:

```bash
cd ~/personal-task-station
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

### 7.2 Deploy CA Certificate

Copy the CA certificate to the client:

```bash
scp server:/etc/pts/certs/ca-cert.pem ~/.pts/certs/
chmod 644 ~/.pts/certs/ca-cert.pem
```

### 7.3 Client Configuration

Launch the client:

```bash
PTS_SERVER_CERT_PATH="$HOME/.pts/certs/ca-cert.pem" \
PTS_SKILL_BASE_URL="https://your-server:8443" \
PTS_SKILL_API_KEY="your-api-key" \
.venv/bin/pts-client
```

In the connection settings UI:

| Field | Value |
|-------|-------|
| Server URL | `https://your-server:8443` |
| API Key | your-api-key |
| Server cert path | `~/.pts/certs/ca-cert.pem` |

### 7.4 mTLS Client Setup (Optional)

If the server has `PTS_SSL_CAFILE` configured:

```bash
# Copy client certificate to client machine
scp server:/etc/pts/certs/client-cert.pem ~/.pts/certs/
scp server:/etc/pts/certs/client-key.pem ~/.pts/certs/
chmod 600 ~/.pts/certs/client-key.pem
```

Set environment variables:

```bash
export PTS_CLIENT_CERT_PATH="$HOME/.pts/certs/client-cert.pem"
export PTS_CLIENT_KEY_PATH="$HOME/.pts/certs/client-key.pem"
export PTS_SERVER_CERT_PATH="$HOME/.pts/certs/ca-cert.pem"
```

## 8. Skill Wrapper Deployment

### 8.1 Environment Configuration

Create `~/.pts/skill.env`:

```bash
export PTS_SKILL_BASE_URL="https://your-server:8443"
export PTS_SKILL_API_KEY="your-api-key"
export PTS_SKILL_SERVER_CERT_PATH="$HOME/.pts/certs/ca-cert.pem"

# For mTLS only:
# export PTS_SKILL_CLIENT_CERT_PATH="$HOME/.pts/certs/client-cert.pem"
# export PTS_SKILL_CLIENT_KEY_PATH="$HOME/.pts/certs/client-key.pem"
```

Source before running skills:

```bash
source ~/.pts/skill.env
.venv/bin/pts-task-skill list --date 2026-04-23
```

## 9. Security Checklist

Before going live, verify every item:

- [ ] API key is at least 32 random characters
- [ ] HTTPS is enabled (`PTS_SSL_CERTFILE` and `PTS_SSL_KEYFILE` are set)
- [ ] HTTP port is blocked by firewall
- [ ] CA certificate is distributed to all authorized clients
- [ ] Private keys (`*-key.pem`) have `600` permissions
- [ ] Database file is outside the web root
- [ ] Server runs as a non-root user (`pts`)
- [ ] Systemd service has `Restart=on-failure`
- [ ] Firewall allows only authorized IP ranges
- [ ] mTLS is enabled for high-security environments (`PTS_SSL_CAFILE`)
- [ ] Client certificates are distributed securely (not via the same channel as the application)
- [ ] Logs are monitored for failed authentication attempts

## 10. Certificate Rotation

Certificates expire. Plan rotation before expiry:

### 10.1 Check Expiry Dates

```bash
openssl x509 -in /etc/pts/certs/server-cert.pem -noout -dates
openssl x509 -in /etc/pts/certs/client-cert.pem -noout -dates
```

### 10.2 Rotate Server Certificate

1. Generate new server certificate (reuse existing CA):

```bash
.venv/bin/python -c "
from scripts.generate_certs import generate_server_cert
from pathlib import Path
ca_key = Path('/etc/pts/certs/ca-key.pem')
ca_cert = Path('/etc/pts/certs/ca-cert.pem')
generate_server_cert(Path('/etc/pts/certs'), ca_key, ca_cert, hostname='your-server', validity_days=365)
"
```

2. Restart the server (zero-downtime not supported in MVP):

```bash
sudo systemctl restart pts-server
```

3. Verify:

```bash
curl --cacert /etc/pts/certs/ca-cert.pem https://your-server:8443/health
```

### 10.3 Rotate CA (Breaking Change)

Rotating the CA requires redistributing the new CA cert to **all** clients:

1. Generate new CA + server + client certs
2. Update server configuration
3. Restart server
4. Distribute new `ca-cert.pem` to every client
5. If using mTLS, distribute new `client-cert.pem` + `client-key.pem`

## 11. Troubleshooting

### 11.1 "SSL certificate verify failed"

**Cause**: Client doesn't have the CA certificate.

**Fix**:
```bash
export PTS_SERVER_CERT_PATH="/path/to/ca-cert.pem"
# or for skills:
export PTS_SKILL_SERVER_CERT_PATH="/path/to/ca-cert.pem"
```

### 11.2 "HTTP is not allowed"

**Cause**: Client is using `http://` instead of `https://`.

**Fix**: Update base URL to `https://your-server:8443`.

### 11.3 "Missing or invalid API key" (401)

**Cause**: `X-API-Key` header is missing or incorrect.

**Fix**: Verify `PTS_API_KEY` matches on both server and client.

### 11.4 mTLS Connection Refused

**Cause**: Server has `PTS_SSL_CAFILE` set but client doesn't present a certificate.

**Fix**: Set `PTS_CLIENT_CERT_PATH` and `PTS_CLIENT_KEY_PATH` on the client.

### 11.5 Port Already in Use

```bash
sudo lsof -i :8443
sudo systemctl stop pts-server
sudo systemctl start pts-server
```

### 11.6 Debug Certificate Issues

```bash
# Inspect server certificate
openssl s_client -connect your-server:8443 -servername your-server </dev/null | openssl x509 -noout -text

# Test with verbose output
curl -v --cacert ca-cert.pem https://your-server:8443/health

# Test mTLS with verbose output
curl -v --cacert ca-cert.pem --cert client-cert.pem --key client-key.pem https://your-server:8443/health
```

## 12. Run Security Validation

After every deployment or configuration change, run the validation script:

```bash
.venv/bin/python scripts/validate_security.py
```

Expected output: `Total: 12/12 passed`

If any check fails, do not expose the server to the network until resolved.
