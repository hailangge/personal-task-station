from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AppSettings:
    database_url: str
    api_key: str
    host: str
    port: int
    allow_insecure_localhost: bool
    server_cert_path: str | None
    client_cert_path: str | None
    client_key_path: str | None
    litellm_base_url: str | None
    litellm_model: str | None
    litellm_api_key: str | None
    request_timeout_seconds: float

    @classmethod
    def load(cls) -> "AppSettings":
        repo_root = Path(os.environ.get("PTS_REPO_ROOT", Path.cwd()))
        default_db = repo_root / ".local" / "personal_task_station.sqlite3"
        return cls(
            database_url=os.environ.get("PTS_DATABASE_URL", f"sqlite:///{default_db}"),
            api_key=os.environ.get("PTS_API_KEY", "dev-token"),
            host=os.environ.get("PTS_HOST", "127.0.0.1"),
            port=int(os.environ.get("PTS_PORT", "8000")),
            allow_insecure_localhost=os.environ.get("PTS_ALLOW_INSECURE_LOCALHOST", "false").lower()
            in {"1", "true", "yes", "on"},
            server_cert_path=os.environ.get("PTS_SERVER_CERT_PATH"),
            client_cert_path=os.environ.get("PTS_CLIENT_CERT_PATH"),
            client_key_path=os.environ.get("PTS_CLIENT_KEY_PATH"),
            litellm_base_url=os.environ.get("PTS_LITELLM_BASE_URL"),
            litellm_model=os.environ.get("PTS_LITELLM_MODEL"),
            litellm_api_key=os.environ.get("PTS_LITELLM_API_KEY"),
            request_timeout_seconds=float(os.environ.get("PTS_REQUEST_TIMEOUT_SECONDS", "15")),
        )
