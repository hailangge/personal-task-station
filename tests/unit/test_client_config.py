from __future__ import annotations

from pathlib import Path

from personal_task_station.client.api_client import build_verify_setting
from personal_task_station.client.config import ClientSettingsStore
from personal_task_station.shared.schemas import ClientSettings, ConnectionConfig


def test_client_settings_round_trip(tmp_path: Path):
    store = ClientSettingsStore(tmp_path / "client.json")
    settings = ClientSettings()
    settings.connection.base_url = "https://example.local:8443"
    settings.desktop.opacity = 0.88
    store.save(settings)
    loaded = store.load()
    assert loaded.connection.base_url == "https://example.local:8443"
    assert loaded.desktop.opacity == 0.88


def test_http_is_rejected():
    config = ConnectionConfig(base_url="http://127.0.0.1:8000")
    try:
        build_verify_setting(config)
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError")


def test_https_with_server_cert_path():
    config = ConnectionConfig(base_url="https://localhost:8443", server_cert_path="/certs/ca-cert.pem")
    assert build_verify_setting(config) == "/certs/ca-cert.pem"


def test_https_with_system_ca_store():
    config = ConnectionConfig(base_url="https://localhost:8443")
    assert build_verify_setting(config) is True
