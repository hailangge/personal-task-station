from __future__ import annotations

import importlib.util
import ssl
import sys
from pathlib import Path

import pytest

from personal_task_station.server.app import _build_ssl_context
from personal_task_station.shared.settings import AppSettings


def _load_generate_certs():
    spec = importlib.util.spec_from_file_location("generate_certs", Path(__file__).parent.parent.parent / "scripts" / "generate_certs.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["generate_certs"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_generate_certs_script_runs(tmp_path: Path):
    certs = _load_generate_certs()

    ca_key, ca_cert = certs.generate_ca(tmp_path, validity_days=1)
    assert ca_key.exists()
    assert ca_cert.exists()

    srv_key, srv_cert = certs.generate_server_cert(tmp_path, ca_key, ca_cert, hostname="test.local", validity_days=1)
    assert srv_key.exists()
    assert srv_cert.exists()

    cli_key, cli_cert = certs.generate_client_cert(tmp_path, ca_key, ca_cert, client_name="test-client", validity_days=1)
    assert cli_key.exists()
    assert cli_cert.exists()


def test_build_ssl_context_without_certs():
    settings = AppSettings(
        database_url="sqlite:///:memory:",
        api_key="test",
        host="127.0.0.1",
        port=8000,
        ssl_certfile=None,
        ssl_keyfile=None,
        ssl_cafile=None,
        server_cert_path=None,
        client_cert_path=None,
        client_key_path=None,
        litellm_base_url=None,
        litellm_model=None,
        litellm_api_key=None,
        request_timeout_seconds=15,
    )
    ctx = _build_ssl_context(settings)
    assert ctx is None


def test_build_ssl_context_with_server_cert_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    certs = _load_generate_certs()
    ca_key, ca_cert = certs.generate_ca(tmp_path, validity_days=1)
    srv_key, srv_cert = certs.generate_server_cert(tmp_path, ca_key, ca_cert, hostname="localhost", validity_days=1)

    monkeypatch.setenv("PTS_SSL_CERTFILE", str(srv_cert))
    monkeypatch.setenv("PTS_SSL_KEYFILE", str(srv_key))
    settings = AppSettings.load()
    ctx = _build_ssl_context(settings)
    assert ctx is not None
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_NONE


def test_build_ssl_context_with_mtls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    certs = _load_generate_certs()
    ca_key, ca_cert = certs.generate_ca(tmp_path, validity_days=1)
    srv_key, srv_cert = certs.generate_server_cert(tmp_path, ca_key, ca_cert, hostname="localhost", validity_days=1)

    monkeypatch.setenv("PTS_SSL_CERTFILE", str(srv_cert))
    monkeypatch.setenv("PTS_SSL_KEYFILE", str(srv_key))
    monkeypatch.setenv("PTS_SSL_CAFILE", str(ca_cert))
    settings = AppSettings.load()
    ctx = _build_ssl_context(settings)
    assert ctx is not None
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_config_endpoint_returns_https_when_ssl_configured(client, auth_headers, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PTS_SSL_CERTFILE", "/certs/server-cert.pem")
    monkeypatch.setenv("PTS_SSL_KEYFILE", "/certs/server-key.pem")
    response = client.get("/config/client-defaults", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["base_url"].startswith("https://")


def test_config_endpoint_returns_http_when_ssl_not_configured(client, auth_headers, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PTS_SSL_CERTFILE", raising=False)
    monkeypatch.delenv("PTS_SSL_KEYFILE", raising=False)
    response = client.get("/config/client-defaults", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["base_url"].startswith("http://")
