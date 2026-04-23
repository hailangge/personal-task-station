from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from personal_task_station.shared.database import get_session
from personal_task_station.shared.security import require_api_key
from personal_task_station.shared.settings import AppSettings


def get_db(request: Request) -> Generator[Session, None, None]:
    database_url = request.app.state.database_url
    yield from get_session(database_url)


def get_settings() -> AppSettings:
    return AppSettings.load()


AuthDependency = Depends(require_api_key)
DBDependency = Depends(get_db)
