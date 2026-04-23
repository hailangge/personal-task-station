from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


PROTECTED_ENDPOINTS = [
    ("GET", "/tasks"),
    ("POST", "/tasks"),
    ("GET", "/tasks/1"),
    ("PUT", "/tasks/1"),
    ("PATCH", "/tasks/1"),
    ("DELETE", "/tasks/1"),
    ("POST", "/tasks/1/status"),
    ("GET", "/tasks/1/history"),
    ("POST", "/tasks/1/subitems"),
    ("PUT", "/tasks/1/subitems/1"),
    ("PATCH", "/tasks/1/subitems/1"),
    ("DELETE", "/tasks/1/subitems/1"),
    ("POST", "/tasks/1/subitems/reorder"),
    ("GET", "/tasks/calendar/summary"),
    ("POST", "/billing/import"),
    ("GET", "/billing/imports"),
    ("POST", "/billing/reanalyze"),
    ("GET", "/billing/summary/monthly"),
    ("GET", "/billing/transactions"),
    ("GET", "/billing/duplicates"),
    ("POST", "/billing/merged/1/undo"),
    ("GET", "/billing/model-calls"),
    ("GET", "/config/client-defaults"),
]


class TestAuthenticationRequired:
    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_missing_api_key_returns_401(self, client: TestClient, method: str, path: str):
        response = client.request(method, path)
        assert response.status_code == 401, f"{method} {path} should require auth"
        assert "API key" in response.json()["detail"]

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_wrong_api_key_returns_401(self, client: TestClient, method: str, path: str):
        response = client.request(method, path, headers={"X-API-Key": "wrong-token"})
        assert response.status_code == 401, f"{method} {path} should reject bad key"
        assert "API key" in response.json()["detail"]


class TestHealthIsPublic:
    def test_health_no_auth(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestConfigDoesNotLeakApiKey:
    def test_client_defaults_masks_api_key(self, client: TestClient, auth_headers: dict[str, str]):
        response = client.get("/config/client-defaults", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert "api_key" in payload
        key = payload["api_key"]
        # The fixture sets PTS_API_KEY="test-token"; the endpoint should mask it.
        assert "test-token" not in key
        assert key.endswith("ken")
        assert key.startswith("****")


class TestAuthenticatedAccess:
    def test_tasks_list_with_valid_key(self, client: TestClient, auth_headers: dict[str, str]):
        response = client.get("/tasks", headers=auth_headers)
        assert response.status_code == 200

    def test_billing_summary_with_valid_key(self, client: TestClient, auth_headers: dict[str, str]):
        response = client.get("/billing/summary/monthly", headers=auth_headers, params={"year": 2026, "month": 1})
        assert response.status_code == 200
