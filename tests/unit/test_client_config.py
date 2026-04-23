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


def test_http_verify_rejected_without_local_dev_flag():
    config = ConnectionConfig(base_url="http://127.0.0.1:8000", allow_insecure_localhost=False)
    try:
        build_verify_setting(config)
    except ValueError as exc:
        assert "localhost" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError")
