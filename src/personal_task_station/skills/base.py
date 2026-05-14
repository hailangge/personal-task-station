from __future__ import annotations

import os
from pathlib import Path

from personal_task_station.client.api_client import ServerApiClient
from personal_task_station.client.config import ClientSettingsStore
from personal_task_station.shared.schemas import ClientSettings, ConnectionConfig


def _default_skill_config_path() -> Path:
    return Path.home() / ".config" / "personal-task-station" / "client_settings.json"


def skill_config_store() -> ClientSettingsStore:
    path = Path(os.environ.get("PTS_SKILL_CONFIG_PATH", str(_default_skill_config_path())))
    return ClientSettingsStore(path)


def load_skill_settings() -> ClientSettings:
    store = skill_config_store()
    if store.path.exists():
        return store.load()
    return ClientSettings(
        connection=ConnectionConfig(
            base_url=os.environ.get("PTS_SKILL_BASE_URL", "http://127.0.0.1:8000"),
            api_key=os.environ.get("PTS_SKILL_API_KEY", os.environ.get("PTS_API_KEY", "dev-token")),
            server_cert_path=os.environ.get("PTS_SKILL_SERVER_CERT_PATH"),
            client_cert_path=os.environ.get("PTS_SKILL_CLIENT_CERT_PATH"),
            client_key_path=os.environ.get("PTS_SKILL_CLIENT_KEY_PATH"),
            allow_insecure_localhost=True,
            timeout_seconds=float(os.environ.get("PTS_SKILL_TIMEOUT_SECONDS", "15")),
        )
    )


def load_skill_connection() -> ConnectionConfig:
    return load_skill_settings().connection


def build_skill_client() -> ServerApiClient:
    return ServerApiClient(load_skill_connection())
