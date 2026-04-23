from __future__ import annotations


def test_task_api_crud_and_calendar(client, auth_headers):
    response = client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Ship MVP",
            "description": "Complete the repository",
            "task_date": "2026-04-23",
            "subitems": [{"title": "Server"}, {"title": "Client"}],
        },
    )
    assert response.status_code == 201, response.text
    task = response.json()
    task_id = task["id"]
    assert task["status"] == "scheduled"

    subitem_id = task["subitems"][0]["id"]
    response = client.patch(
        f"/tasks/{task_id}/subitems/{subitem_id}",
        headers=auth_headers,
        json={"status": "completed"},
    )
    assert response.status_code == 200

    response = client.get("/tasks", headers=auth_headers, params={"task_date": "2026-04-23"})
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get(
        "/tasks/calendar/summary",
        headers=auth_headers,
        params={"start_date": "2026-04-01", "end_date": "2026-04-30"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["in_progress"] == 1

    response = client.get(f"/tasks/{task_id}/history", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 2
