from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx

from personal_task_station.shared.schemas import (
    CalendarDaySummary,
    ConnectionConfig,
    ImportJobRead,
    MonthlySummary,
    NormalizedTransactionRead,
    TaskCreate,
    TaskRead,
    TaskStatusChange,
    TaskSubItemCreate,
    TaskUpdate,
)


def build_verify_setting(config: ConnectionConfig):
    parsed = urlparse(config.base_url)
    if parsed.scheme == "http":
        raise ValueError("HTTP is not allowed. Use HTTPS only.")
    if config.server_cert_path:
        return str(Path(config.server_cert_path))
    return config.verify_tls


def build_cert_setting(config: ConnectionConfig):
    if config.client_cert_path and config.client_key_path:
        return (config.client_cert_path, config.client_key_path)
    if config.client_cert_path:
        return config.client_cert_path
    return None


class ServerApiClient:
    def __init__(
        self,
        config: ConnectionConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        self.config = config
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.config.base_url.rstrip("/"),
            headers={"X-API-Key": self.config.api_key},
            timeout=self.config.timeout_seconds,
            verify=build_verify_setting(self.config),
            cert=build_cert_setting(self.config),
            transport=self._transport,
        )

    def health(self) -> dict:
        with self._client() as client:
            return client.get("/health").json()

    def list_tasks(self, **params) -> list[TaskRead]:
        with self._client() as client:
            response = client.get("/tasks", params=params)
            response.raise_for_status()
            return [TaskRead.model_validate(item) for item in response.json()]

    def get_task(self, task_id: int) -> TaskRead:
        with self._client() as client:
            response = client.get(f"/tasks/{task_id}")
            response.raise_for_status()
            return TaskRead.model_validate(response.json())

    def create_task(self, payload: TaskCreate) -> TaskRead:
        with self._client() as client:
            response = client.post("/tasks", json=payload.model_dump(mode="json"))
            response.raise_for_status()
            return TaskRead.model_validate(response.json())

    def update_task(self, task_id: int, payload: TaskUpdate) -> TaskRead:
        with self._client() as client:
            response = client.patch(f"/tasks/{task_id}", json=payload.model_dump(mode="json", exclude_unset=True))
            response.raise_for_status()
            return TaskRead.model_validate(response.json())

    def change_task_status(self, task_id: int, payload: TaskStatusChange) -> TaskRead:
        with self._client() as client:
            response = client.post(f"/tasks/{task_id}/status", json=payload.model_dump(mode="json"))
            response.raise_for_status()
            return TaskRead.model_validate(response.json())

    def add_subitem(self, task_id: int, payload: TaskSubItemCreate) -> dict:
        with self._client() as client:
            response = client.post(f"/tasks/{task_id}/subitems", json=payload.model_dump(mode="json"))
            response.raise_for_status()
            return response.json()

    def delete_task(self, task_id: int) -> None:
        with self._client() as client:
            response = client.delete(f"/tasks/{task_id}")
            response.raise_for_status()

    def reorder_subitems(self, task_id: int, ordered_ids: list[int]) -> TaskRead:
        with self._client() as client:
            response = client.post(f"/tasks/{task_id}/subitems/reorder", json=ordered_ids)
            response.raise_for_status()
            return TaskRead.model_validate(response.json())

    def undo_merge(self, merged_transaction_id: int) -> dict:
        with self._client() as client:
            response = client.post(f"/billing/merged/{merged_transaction_id}/undo")
            response.raise_for_status()
            return response.json()

    def calendar_summary(self, start_date: date, end_date: date) -> list[CalendarDaySummary]:
        with self._client() as client:
            response = client.get(
                "/tasks/calendar/summary",
                params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            )
            response.raise_for_status()
            return [CalendarDaySummary.model_validate(item) for item in response.json()]

    def monthly_summary(self, year: int, month: int) -> MonthlySummary:
        with self._client() as client:
            response = client.get("/billing/summary/monthly", params={"year": year, "month": month})
            response.raise_for_status()
            return MonthlySummary.model_validate(response.json())

    def list_transactions(self, **params) -> list[NormalizedTransactionRead]:
        with self._client() as client:
            response = client.get("/billing/transactions", params=params)
            response.raise_for_status()
            return [NormalizedTransactionRead.model_validate(item) for item in response.json()]

    def import_billing_file(self, source_name: str, file_path: str | Path) -> ImportJobRead:
        path = Path(file_path)
        with self._client() as client:
            with path.open("rb") as handle:
                response = client.post(
                    "/billing/import",
                    data={"source_name": source_name},
                    files={"file": (path.name, handle, "text/csv")},
                )
            response.raise_for_status()
            return ImportJobRead.model_validate(response.json())

    def list_duplicates(self):
        with self._client() as client:
            response = client.get("/billing/duplicates")
            response.raise_for_status()
            return response.json()

    def reanalyze(self, import_job_id: int | None = None) -> dict:
        with self._client() as client:
            response = client.post("/billing/reanalyze", json={"import_job_id": import_job_id})
            response.raise_for_status()
            return response.json()


class InMemoryApiClient:
    """Test-friendly drop-in replacement for the UI."""

    def __init__(self):
        self.tasks: list[TaskRead] = []
        self.calendar_items: list[CalendarDaySummary] = []
        self.summary: MonthlySummary | None = None
        self.transactions: list[NormalizedTransactionRead] = []

    def health(self) -> dict:
        return {"status": "ok"}

    def list_tasks(self, **params) -> list[TaskRead]:
        task_date = params.get("task_date")
        if not task_date:
            return list(self.tasks)
        return [task for task in self.tasks if task.task_date and task.task_date.isoformat() == task_date]

    def get_task(self, task_id: int) -> TaskRead:
        return next(task for task in self.tasks if task.id == task_id)

    def create_task(self, payload: TaskCreate) -> TaskRead:
        task = TaskRead.model_validate(
            {
                **payload.model_dump(mode="json"),
                "id": len(self.tasks) + 1,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "history": [],
                "subitems": [item.model_dump(mode="json") | {"id": idx + 1, "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"} for idx, item in enumerate(payload.subitems)],
            }
        )
        self.tasks.append(task)
        return task

    def update_task(self, task_id: int, payload: TaskUpdate) -> TaskRead:
        current = self.get_task(task_id)
        updated = current.model_copy(update=payload.model_dump(exclude_unset=True))
        self.tasks = [updated if task.id == task_id else task for task in self.tasks]
        return updated

    def change_task_status(self, task_id: int, payload: TaskStatusChange) -> TaskRead:
        return self.update_task(task_id, TaskUpdate(status=payload.status))

    def calendar_summary(self, start_date: date, end_date: date) -> list[CalendarDaySummary]:
        return [item for item in self.calendar_items if start_date <= item.date <= end_date]

    def monthly_summary(self, year: int, month: int) -> MonthlySummary:
        if not self.summary:
            raise RuntimeError("No summary configured")
        return self.summary

    def list_transactions(self, **params) -> list[NormalizedTransactionRead]:
        return list(self.transactions)
