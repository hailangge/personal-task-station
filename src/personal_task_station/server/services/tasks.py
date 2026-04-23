from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from personal_task_station.shared.enums import SubItemStatus, TaskStatus
from personal_task_station.shared.models import AuditLog, Task, TaskStatusHistory, TaskSubItem
from personal_task_station.shared.schemas import (
    CalendarDaySummary,
    TaskCreate,
    TaskStatusChange,
    TaskSubItemCreate,
    TaskSubItemUpdate,
    TaskUpdate,
)


class TaskService:
    def __init__(self, session: Session):
        self.session = session

    def list_tasks(
        self,
        *,
        task_date: date | None = None,
        status: TaskStatus | None = None,
        query: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Task]:
        stmt = select(Task).options(
            selectinload(Task.subitems),
            selectinload(Task.history),
        )
        if status:
            stmt = stmt.where(Task.status == status)
        if query:
            pattern = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    Task.title.ilike(pattern),
                    Task.description.ilike(pattern),
                    Task.note.ilike(pattern),
                )
            )
        if task_date:
            stmt = stmt.where(
                or_(
                    Task.task_date == task_date,
                    func.date(Task.start_at) == task_date,
                    func.date(Task.due_at) == task_date,
                )
            )
        if start_date:
            stmt = stmt.where(
                or_(
                    Task.task_date >= start_date,
                    Task.start_at >= start_date,
                    Task.due_at >= start_date,
                )
            )
        if end_date:
            stmt = stmt.where(
                or_(
                    Task.task_date <= end_date,
                    Task.start_at <= end_date,
                    Task.due_at <= end_date,
                )
            )
        tasks = list(self.session.scalars(stmt).all())
        if task_date:
            tasks = [task for task in tasks if self._task_anchor_date(task) == task_date]
        if start_date:
            tasks = [task for task in tasks if self._task_anchor_date(task) and self._task_anchor_date(task) >= start_date]
        if end_date:
            tasks = [task for task in tasks if self._task_anchor_date(task) and self._task_anchor_date(task) <= end_date]
        return tasks

    def get_task(self, task_id: int) -> Task | None:
        stmt = (
            select(Task)
            .where(Task.id == task_id)
            .options(selectinload(Task.subitems), selectinload(Task.history))
        )
        return self.session.scalar(stmt)

    def create_task(self, payload: TaskCreate) -> Task:
        task = Task(**payload.model_dump(exclude={"subitems"}))
        self.session.add(task)
        self.session.flush()
        for index, subitem_payload in enumerate(payload.subitems):
            subitem = TaskSubItem(
                task_id=task.id,
                sort_order=index,
                **subitem_payload.model_dump(exclude={"sort_order"}),
            )
            self.session.add(subitem)
        self._record_status_change(task, None, task.status, reason="Task created", source="api")
        self.session.flush()
        self._sync_task_status_from_subitems(task, reason="Initial subitem synchronization")
        self._record_audit("task.created", "task", str(task.id), {"title": task.title})
        return self.get_task(task.id) or task

    def update_task(self, task_id: int, payload: TaskUpdate) -> Task:
        task = self._require_task(task_id)
        changes = payload.model_dump(exclude_unset=True)
        next_status = changes.pop("status", None)
        for key, value in changes.items():
            setattr(task, key, value)
        if next_status and next_status != task.status:
            self.change_status(task_id, TaskStatusChange(status=next_status, reason="Task updated", source="api"))
            task = self._require_task(task_id)
        self._record_audit("task.updated", "task", str(task.id), {"fields": sorted(changes)})
        self.session.flush()
        return self.get_task(task.id) or task

    def delete_task(self, task_id: int) -> None:
        task = self._require_task(task_id)
        self._record_audit("task.deleted", "task", str(task.id), {"title": task.title})
        self.session.delete(task)

    def change_status(self, task_id: int, change: TaskStatusChange) -> Task:
        task = self._require_task(task_id)
        if task.status != change.status:
            old_status = task.status
            task.status = change.status
            self._record_status_change(task, old_status, change.status, change.reason, change.source)
            self._record_audit(
                "task.status_changed",
                "task",
                str(task.id),
                {"from": old_status.value, "to": change.status.value, "reason": change.reason},
            )
        self.session.flush()
        return self.get_task(task.id) or task

    def add_subitem(self, task_id: int, payload: TaskSubItemCreate) -> TaskSubItem:
        task = self._require_task(task_id)
        existing_orders = [item.sort_order for item in task.subitems]
        sort_order = payload.sort_order if payload.sort_order else (max(existing_orders, default=-1) + 1)
        subitem = TaskSubItem(task_id=task.id, sort_order=sort_order, **payload.model_dump(exclude={"sort_order"}))
        self.session.add(subitem)
        self.session.flush()
        self._sync_task_status_from_subitems(task, reason="Subitem added")
        self._record_audit("task.subitem_added", "task", str(task.id), {"subitem_id": subitem.id})
        return subitem

    def update_subitem(self, task_id: int, subitem_id: int, payload: TaskSubItemUpdate) -> TaskSubItem:
        task = self._require_task(task_id)
        subitem = self._require_subitem(task_id, subitem_id)
        changes = payload.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(subitem, key, value)
        self.session.flush()
        self._sync_task_status_from_subitems(task, reason="Subitem updated")
        self._record_audit("task.subitem_updated", "task", str(task.id), {"subitem_id": subitem.id, "fields": sorted(changes)})
        return subitem

    def delete_subitem(self, task_id: int, subitem_id: int) -> None:
        task = self._require_task(task_id)
        subitem = self._require_subitem(task_id, subitem_id)
        self.session.delete(subitem)
        self.session.flush()
        self._sync_task_status_from_subitems(task, reason="Subitem deleted")
        self._record_audit("task.subitem_deleted", "task", str(task.id), {"subitem_id": subitem_id})

    def reorder_subitems(self, task_id: int, ordered_ids: list[int]) -> Task:
        task = self._require_task(task_id)
        subitems = {item.id: item for item in task.subitems}
        for index, subitem_id in enumerate(ordered_ids):
            if subitem_id in subitems:
                subitems[subitem_id].sort_order = index
        self.session.flush()
        self._record_audit("task.subitem_reordered", "task", str(task.id), {"ordered_ids": ordered_ids})
        return self.get_task(task.id) or task

    def get_history(self, task_id: int) -> list[TaskStatusHistory]:
        task = self._require_task(task_id)
        return list(task.history)

    def calendar_summary(self, start_date: date, end_date: date) -> list[CalendarDaySummary]:
        tasks = self.list_tasks(start_date=start_date, end_date=end_date)
        grouped: dict[date, list[Task]] = defaultdict(list)
        for task in tasks:
            anchor = self._task_anchor_date(task)
            if anchor:
                grouped[anchor].append(task)

        summaries: list[CalendarDaySummary] = []
        for day in sorted(grouped):
            counts = Counter(task.status for task in grouped[day])
            dominant = None
            for candidate in (
                TaskStatus.IN_PROGRESS,
                TaskStatus.ON_HOLD,
                TaskStatus.SCHEDULED,
                TaskStatus.COMPLETED,
                TaskStatus.CANCELLED,
            ):
                if counts.get(candidate):
                    dominant = candidate
                    break
            summaries.append(
                CalendarDaySummary(
                    date=day,
                    total=len(grouped[day]),
                    scheduled=counts.get(TaskStatus.SCHEDULED, 0),
                    in_progress=counts.get(TaskStatus.IN_PROGRESS, 0),
                    on_hold=counts.get(TaskStatus.ON_HOLD, 0),
                    completed=counts.get(TaskStatus.COMPLETED, 0),
                    cancelled=counts.get(TaskStatus.CANCELLED, 0),
                    dominant_status=dominant,
                )
            )
        return summaries

    def _require_task(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        return task

    def _require_subitem(self, task_id: int, subitem_id: int) -> TaskSubItem:
        task = self._require_task(task_id)
        for subitem in task.subitems:
            if subitem.id == subitem_id:
                return subitem
        raise ValueError(f"Subitem {subitem_id} not found for task {task_id}")

    def _task_anchor_date(self, task: Task) -> date | None:
        if task.task_date:
            return task.task_date
        if task.start_at:
            return task.start_at.date()
        if task.due_at:
            return task.due_at.date()
        return None

    def _record_status_change(
        self,
        task: Task,
        old_status: TaskStatus | None,
        new_status: TaskStatus,
        reason: str,
        source: str,
    ) -> None:
        history = TaskStatusHistory(
            old_status=old_status,
            new_status=new_status,
            reason=reason,
            source=source,
        )
        task.history.append(history)

    def _sync_task_status_from_subitems(self, task: Task, reason: str) -> None:
        if not task.subitems or task.status == TaskStatus.CANCELLED:
            return
        statuses = {item.status for item in task.subitems}
        target_status: TaskStatus | None = None
        if statuses and statuses == {SubItemStatus.COMPLETED}:
            target_status = TaskStatus.COMPLETED
        elif SubItemStatus.IN_PROGRESS in statuses or (
            SubItemStatus.COMPLETED in statuses and SubItemStatus.PENDING in statuses
        ):
            target_status = TaskStatus.IN_PROGRESS
        elif SubItemStatus.PENDING in statuses and task.status == TaskStatus.COMPLETED:
            target_status = TaskStatus.IN_PROGRESS

        if target_status and target_status != task.status:
            previous = task.status
            task.status = target_status
            self._record_status_change(task, previous, target_status, reason, "system")

    def _record_audit(self, action: str, entity_type: str, entity_id: str, details: dict) -> None:
        self.session.add(
            AuditLog(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details,
            )
        )
