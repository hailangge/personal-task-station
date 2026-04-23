from __future__ import annotations

import json
import os
from pathlib import Path

from personal_task_station.shared.schemas import ClientSettings


def default_config_path() -> Path:
    override = os.environ.get("PTS_CLIENT_CONFIG_PATH")
    if override:
        return Path(override)
    return Path.cwd() / ".local" / "client_settings.json"


class ClientSettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_config_path()

    def load(self) -> ClientSettings:
        if not self.path.exists():
            return ClientSettings()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return ClientSettings.model_validate(payload)

    def save(self, settings: ClientSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(settings.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
