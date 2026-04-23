from __future__ import annotations

from datetime import date

from personal_task_station.server.services.tasks import TaskService
from personal_task_station.shared.database import Base, get_engine, session_scope
from personal_task_station.shared.enums import SubItemStatus, TaskStatus
from personal_task_station.shared.schemas import TaskCreate, TaskSubItemCreate, TaskSubItemUpdate


def test_task_service_syncs_status_with_subitems(database_url: str):
    Base.metadata.create_all(bind=get_engine(database_url))
    with session_scope(database_url) as session:
        service = TaskService(session)
        task = service.create_task(
            TaskCreate(
                title="Prepare release",
                task_date=date(2026, 4, 23),
                subitems=[
                    TaskSubItemCreate(title="Server"),
                    TaskSubItemCreate(title="Client"),
                ],
            )
        )
        assert task.status == TaskStatus.SCHEDULED

        first = task.subitems[0]
        service.update_subitem(task.id, first.id, TaskSubItemUpdate(status=SubItemStatus.COMPLETED))
        updated = service.get_task(task.id)
        assert updated is not None
        assert updated.status == TaskStatus.IN_PROGRESS

        second = updated.subitems[1]
        service.update_subitem(task.id, second.id, TaskSubItemUpdate(status=SubItemStatus.COMPLETED))
        completed = service.get_task(task.id)
        assert completed is not None
        assert completed.status == TaskStatus.COMPLETED
        assert [item.new_status for item in completed.history][-1] == TaskStatus.COMPLETED


def test_calendar_summary_prefers_in_progress(database_url: str):
    Base.metadata.create_all(bind=get_engine(database_url))
    with session_scope(database_url) as session:
        service = TaskService(session)
        service.create_task(TaskCreate(title="A", task_date=date(2026, 4, 10), status=TaskStatus.COMPLETED))
        service.create_task(TaskCreate(title="B", task_date=date(2026, 4, 10), status=TaskStatus.IN_PROGRESS))
        summary = service.calendar_summary(date(2026, 4, 1), date(2026, 4, 30))
        assert len(summary) == 1
        assert summary[0].dominant_status == TaskStatus.IN_PROGRESS
        assert summary[0].completed == 1
