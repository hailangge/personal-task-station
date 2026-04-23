from __future__ import annotations

import os
from pathlib import Path

from personal_task_station.client.api_client import ServerApiClient
from personal_task_station.client.config import ClientSettingsStore
from personal_task_station.shared.schemas import ConnectionConfig


def load_skill_connection() -> ConnectionConfig:
    config_path = os.environ.get("PTS_SKILL_CONFIG_PATH")
    if config_path and Path(config_path).exists():
        return ClientSettingsStore(Path(config_path)).load().connection
    return ConnectionConfig(
        base_url=os.environ.get("PTS_SKILL_BASE_URL", "http://127.0.0.1:8000"),
        api_key=os.environ.get("PTS_SKILL_API_KEY", os.environ.get("PTS_API_KEY", "dev-token")),
        server_cert_path=os.environ.get("PTS_SKILL_SERVER_CERT_PATH"),
        client_cert_path=os.environ.get("PTS_SKILL_CLIENT_CERT_PATH"),
        client_key_path=os.environ.get("PTS_SKILL_CLIENT_KEY_PATH"),
        allow_insecure_localhost=os.environ.get("PTS_SKILL_ALLOW_INSECURE_LOCALHOST", "false").lower()
        in {"1", "true", "yes", "on"},
        timeout_seconds=float(os.environ.get("PTS_SKILL_TIMEOUT_SECONDS", "15")),
    )


def build_skill_client() -> ServerApiClient:
    return ServerApiClient(load_skill_connection())
