from __future__ import annotations

import httpx

from personal_task_station.client.api_client import ServerApiClient
from personal_task_station.shared.schemas import ConnectionConfig
from personal_task_station.skills.finance_skill import FinanceSkill
from personal_task_station.skills.task_skill import TaskSkill


def _build_test_client(test_client):
    def handler(request: httpx.Request) -> httpx.Response:
        query = f"?{request.url.query.decode()}" if request.url.query else ""
        response = test_client.request(
            request.method,
            f"{request.url.path}{query}",
            headers=dict(request.headers),
            content=request.read(),
        )
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )

    transport = httpx.MockTransport(handler)
    config = ConnectionConfig(base_url="https://127.0.0.1:8000", api_key="test-token")
    return ServerApiClient(config, transport=transport)


def test_skill_wrappers_call_server(client, auth_headers, monkeypatch):
    client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Via skill", "task_date": "2026-04-23"},
    )

    skill_client = _build_test_client(client)
    monkeypatch.setattr("personal_task_station.skills.task_skill.build_skill_client", lambda: skill_client)
    monkeypatch.setattr("personal_task_station.skills.finance_skill.build_skill_client", lambda: skill_client)

    task_skill = TaskSkill()
    tasks = task_skill.tasks_for_day(__import__("datetime").date(2026, 4, 23))
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Via skill"

    created = task_skill.create_task(
        title="Skill aliases",
        scheduled_date="2026-05-14",
        start_time="2026-05-14T09:00:00",
        due_time="2026-05-14T10:00:00",
        notes="Skill note",
        priority="critical",
    )
    assert created["task_date"] == "2026-05-14"
    assert created["scheduled_date"] == "2026-05-14"
    assert created["start_at"] == "2026-05-14T09:00:00"
    assert created["start_time"] == "2026-05-14T09:00:00"
    assert created["due_at"] == "2026-05-14T10:00:00"
    assert created["due_time"] == "2026-05-14T10:00:00"
    assert created["note"] == "Skill note"
    assert created["notes"] == "Skill note"
    assert created["priority"] == 1

    updated = task_skill.update_task(created["id"], notes="Updated skill note", priority="5")
    assert updated["note"] == "Updated skill note"
    assert updated["notes"] == "Updated skill note"
    assert updated["priority"] == 5

    finance_skill = FinanceSkill()
    summary = finance_skill.monthly_summary(2026, 3)
    assert summary["month"] == "2026-03"
