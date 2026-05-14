from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx

from personal_task_station.shared.schemas import (
    CalendarDaySummary,
    ConnectionConfig,
    EmailAccountCreate,
    EmailAccountRead,
    EmailImportResult,
    ImportJobRead,
    MonthlySummary,
    NormalizedTransactionRead,
    TaskCreate,
    TaskRead,
    TaskStatusChange,
    TaskStatusHistoryRead,
    TaskSubItemCreate,
    TaskSubItemRead,
    TaskSubItemUpdate,
    TaskUpdate,
)


def build_verify_setting(config: ConnectionConfig):
    parsed = urlparse(config.base_url)
    if parsed.scheme == "http":
        if config.allow_insecure_localhost and parsed.hostname in ("localhost", "127.0.0.1", "::1"):
            return True
        raise ValueError(
            "HTTPS is required unless local HTTP is explicitly enabled for localhost."
        )
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

    def add_subitem(self, task_id: int, payload: TaskSubItemCreate) -> TaskSubItemRead:
        with self._client() as client:
            response = client.post(f"/tasks/{task_id}/subitems", json=payload.model_dump(mode="json"))
            response.raise_for_status()
            return TaskSubItemRead.model_validate(response.json())

    def update_subitem(self, task_id: int, subitem_id: int, payload: TaskSubItemUpdate) -> TaskSubItemRead:
        with self._client() as client:
            response = client.patch(
                f"/tasks/{task_id}/subitems/{subitem_id}",
                json=payload.model_dump(mode="json", exclude_unset=True),
            )
            response.raise_for_status()
            return TaskSubItemRead.model_validate(response.json())

    def toggle_subitem(self, task_id: int, subitem_id: int) -> TaskSubItemRead:
        with self._client() as client:
            response = client.post(f"/tasks/{task_id}/subitems/{subitem_id}/toggle")
            response.raise_for_status()
            return TaskSubItemRead.model_validate(response.json())

    def delete_subitem(self, task_id: int, subitem_id: int) -> None:
        with self._client() as client:
            response = client.delete(f"/tasks/{task_id}/subitems/{subitem_id}")
            response.raise_for_status()

    def task_history(self, task_id: int) -> list[TaskStatusHistoryRead]:
        with self._client() as client:
            response = client.get(f"/tasks/{task_id}/history")
            response.raise_for_status()
            return [TaskStatusHistoryRead.model_validate(item) for item in response.json()]

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

    def calendar_month(self, year: int, month: int) -> list[CalendarDaySummary]:
        with self._client() as client:
            response = client.get("/tasks/calendar/month", params={"year": year, "month": month})
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

    def sync_email_accounts(
        self, since_date: date | None = None, timeout: float = 120.0
    ) -> list[ImportJobRead]:
        params: dict = {}
        if since_date:
            params["since_date"] = since_date.isoformat()
        with self._client() as client:
            response = client.post("/email-import/sync", params=params, timeout=timeout)
            response.raise_for_status()
            return [ImportJobRead.model_validate(item) for item in response.json()]

    def create_email_account(self, payload: EmailAccountCreate) -> EmailAccountRead:
        with self._client() as client:
            response = client.post("/email-import/accounts", json=payload.model_dump(mode="json"))
            response.raise_for_status()
            return EmailAccountRead.model_validate(response.json())

    def list_email_accounts(self) -> list[EmailAccountRead]:
        with self._client() as client:
            response = client.get("/email-import/accounts")
            response.raise_for_status()
            return [EmailAccountRead.model_validate(item) for item in response.json()]

    def trigger_email_import(
        self,
        account_id: int,
        since_date: date | None = None,
        ignore_seen: bool = False,
        timeout: float = 120.0,
    ) -> ImportJobRead:
        params: dict = {}
        if since_date:
            params["since_date"] = since_date.isoformat()
        if ignore_seen:
            params["ignore_seen"] = "true"
        with self._client() as client:
            response = client.post(
                f"/email-import/accounts/{account_id}/import",
                params=params,
                timeout=timeout,
            )
            response.raise_for_status()
            return ImportJobRead.model_validate(response.json())


class InMemoryApiClient:
    """Test-friendly drop-in replacement for the UI."""

    def __init__(self):
        self.tasks: list[TaskRead] = []
        self.calendar_items: list[CalendarDaySummary] = []
        self.summary: MonthlySummary | None = None
        self.transactions: list[NormalizedTransactionRead] = []
        self._next_subitem_id = 1

    def health(self) -> dict:
        return {"status": "ok"}

    def list_tasks(self, **params) -> list[TaskRead]:
        task_date = params.get("task_date")
        status = params.get("status")
        query = params.get("query")
        tasks = list(self.tasks)
        if task_date:
            tasks = [task for task in tasks if task.task_date and task.task_date.isoformat() == task_date]
        if status:
            tasks = [task for task in tasks if task.status.value == status]
        if query:
            needle = str(query).lower()
            tasks = [task for task in tasks if needle in task.title.lower() or needle in task.description.lower() or needle in task.note.lower()]
        return tasks

    def get_task(self, task_id: int) -> TaskRead:
        return next(task for task in self.tasks if task.id == task_id)

    def create_task(self, payload: TaskCreate) -> TaskRead:
        subitems = []
        for item in payload.subitems:
            subitems.append(
                item.model_dump(mode="json")
                | {
                    "id": self._next_subitem_id,
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
                }
            )
            self._next_subitem_id += 1
        task = TaskRead.model_validate(
            {
                **payload.model_dump(mode="json"),
                "id": len(self.tasks) + 1,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "history": [],
                "subitems": subitems,
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

    def delete_task(self, task_id: int) -> None:
        self.tasks = [task for task in self.tasks if task.id != task_id]

    def add_subitem(self, task_id: int, payload: TaskSubItemCreate) -> TaskSubItemRead:
        task = self.get_task(task_id)
        subitem = TaskSubItemRead.model_validate(
            payload.model_dump(mode="json")
            | {
                "id": self._next_subitem_id,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }
        )
        self._next_subitem_id += 1
        updated = task.model_copy(update={"subitems": [*task.subitems, subitem]})
        self.tasks = [updated if item.id == task_id else item for item in self.tasks]
        return subitem

    def update_subitem(self, task_id: int, subitem_id: int, payload: TaskSubItemUpdate) -> TaskSubItemRead:
        task = self.get_task(task_id)
        changes = payload.model_dump(exclude_unset=True)
        updated_subitems = []
        selected = None
        for subitem in task.subitems:
            if subitem.id == subitem_id:
                selected = subitem.model_copy(update=changes)
                updated_subitems.append(selected)
            else:
                updated_subitems.append(subitem)
        if selected is None:
            raise KeyError(subitem_id)
        updated = task.model_copy(update={"subitems": updated_subitems})
        self.tasks = [updated if item.id == task_id else item for item in self.tasks]
        return selected

    def toggle_subitem(self, task_id: int, subitem_id: int) -> TaskSubItemRead:
        from personal_task_station.shared.enums import SubItemStatus

        subitem = next(item for item in self.get_task(task_id).subitems if item.id == subitem_id)
        status = SubItemStatus.PENDING if subitem.completed else SubItemStatus.COMPLETED
        return self.update_subitem(task_id, subitem_id, TaskSubItemUpdate(status=status))

    def delete_subitem(self, task_id: int, subitem_id: int) -> None:
        task = self.get_task(task_id)
        updated = task.model_copy(update={"subitems": [item for item in task.subitems if item.id != subitem_id]})
        self.tasks = [updated if item.id == task_id else item for item in self.tasks]

    def task_history(self, task_id: int) -> list[TaskStatusHistoryRead]:
        return list(self.get_task(task_id).history)

    def calendar_summary(self, start_date: date, end_date: date) -> list[CalendarDaySummary]:
        return [item for item in self.calendar_items if start_date <= item.date <= end_date]

    def calendar_month(self, year: int, month: int) -> list[CalendarDaySummary]:
        return [item for item in self.calendar_items if item.date.year == year and item.date.month == month]

    def monthly_summary(self, year: int, month: int) -> MonthlySummary:
        if not self.summary:
            raise RuntimeError("No summary configured")
        return self.summary

    def list_transactions(self, **params) -> list[NormalizedTransactionRead]:
        return list(self.transactions)
