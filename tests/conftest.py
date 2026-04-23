from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from personal_task_station.server.app import create_app
from personal_task_station.shared.database import Base, get_engine, reset_database_caches


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def auth_headers(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setenv("PTS_API_KEY", "test-token")
    return {"X-API-Key": "test-token"}


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.sqlite3'}"


@pytest.fixture
def app(database_url: str, auth_headers: dict[str, str]):
    reset_database_caches()
    app = create_app(database_url)
    Base.metadata.create_all(bind=get_engine(database_url))
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_transactions_csv() -> bytes:
    return Path("fixtures/sample_transactions.csv").read_bytes()
