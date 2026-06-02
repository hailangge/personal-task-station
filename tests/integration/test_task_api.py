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

    response = client.post(f"/tasks/{task_id}/subitems/{subitem_id}/toggle", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] in {"pending", "completed"}

    response = client.get(
        "/tasks/calendar/month",
        headers=auth_headers,
        params={"year": 2026, "month": 4},
    )
    assert response.status_code == 200
    assert response.json()[0]["has_pinned"] is False


def test_task_api_accepts_spec_field_names(client, auth_headers):
    response = client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Spec fields",
            "scheduled_date": "2026-05-14",
            "start_time": "2026-05-14T09:00:00",
            "due_time": "2026-05-14T10:00:00",
            "notes": "Uses public field names",
            "status": "blocked",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["task_date"] == "2026-05-14"
    assert payload["scheduled_date"] == "2026-05-14"
    assert payload["notes"] == "Uses public field names"
    assert payload["status"] == "blocked"

    response = client.patch(
        f"/tasks/{payload['id']}",
        headers=auth_headers,
        json={
            "scheduled_date": "2026-05-15",
            "start_time": "2026-05-15T11:00:00",
            "due_time": "2026-05-15T12:00:00",
            "notes": "Updated public aliases",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["task_date"] == "2026-05-15"
    assert payload["scheduled_date"] == "2026-05-15"
    assert payload["start_at"] == "2026-05-15T11:00:00"
    assert payload["start_time"] == "2026-05-15T11:00:00"
    assert payload["due_at"] == "2026-05-15T12:00:00"
    assert payload["due_time"] == "2026-05-15T12:00:00"
    assert payload["note"] == "Updated public aliases"
    assert payload["notes"] == "Updated public aliases"


def test_task_api_accepts_priority_labels_and_numeric_strings(client, auth_headers):
    response = client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Priority label", "priority": "high"},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["priority"] == 2

    response = client.patch(
        f"/tasks/{payload['id']}",
        headers=auth_headers,
        json={"priority": "5"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["priority"] == 5


def test_task_api_rejects_unknown_priority_label(client, auth_headers):
    response = client.post(
        "/tasks",
        headers=auth_headers,
        json={"title": "Bad priority", "priority": "urgent"},
    )
    assert response.status_code == 422


def test_create_task_with_completed_subitem_syncs_status(client, auth_headers):
    response = client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Auto sync on create",
            "subitems": [{"title": "Done", "status": "completed"}],
        },
    )
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["status"] == "completed"
    history = task["history"]
    assert len(history) == 2
    assert all(isinstance(entry["id"], int) for entry in history)
    assert history[1]["new_status"] == "completed"


def test_reorder_subitems_response_and_get_use_requested_order(client, auth_headers):
    response = client.post(
        "/tasks",
        headers=auth_headers,
        json={
            "title": "Reorder response",
            "subitems": [
                {"title": "First"},
                {"title": "Second"},
                {"title": "Third"},
            ],
        },
    )
    assert response.status_code == 201, response.text
    task = response.json()
    task_id = task["id"]
    requested_order = [item["id"] for item in reversed(task["subitems"])]

    response = client.post(
        f"/tasks/{task_id}/subitems/reorder",
        headers=auth_headers,
        json=requested_order,
    )
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["subitems"]] == requested_order

    response = client.get(f"/tasks/{task_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["subitems"]] == requested_order
