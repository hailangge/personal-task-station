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
        assert summary[0].incomplete == 1


def test_calendar_summary_includes_priority_pinned_and_blocked(database_url: str):
    Base.metadata.create_all(bind=get_engine(database_url))
    with session_scope(database_url) as session:
        service = TaskService(session)
        service.create_task(TaskCreate(title="Pinned", task_date=date(2026, 5, 1), priority=2, is_pinned=True))
        service.create_task(TaskCreate(title="Blocked", task_date=date(2026, 5, 1), status=TaskStatus.BLOCKED, priority=1))

        summary = service.calendar_summary_for_month(2026, 5)[0]
        assert summary.blocked == 1
        assert summary.on_hold == 1
        assert summary.has_pinned is True
        assert summary.highest_priority == 1
        assert "blocked:1" in summary.status_summary


def test_toggle_subitem_switches_completion(database_url: str):
    Base.metadata.create_all(bind=get_engine(database_url))
    with session_scope(database_url) as session:
        service = TaskService(session)
        task = service.create_task(TaskCreate(title="Toggle", subitems=[TaskSubItemCreate(title="One")]))
        subitem_id = task.subitems[0].id
        assert service.toggle_subitem(task.id, subitem_id).status == SubItemStatus.COMPLETED
        assert service.toggle_subitem(task.id, subitem_id).status == SubItemStatus.PENDING


def test_add_subitem_refreshes_loaded_task_and_same_session_get(database_url: str):
    Base.metadata.create_all(bind=get_engine(database_url))
    with session_scope(database_url) as session:
        service = TaskService(session)
        task = service.create_task(TaskCreate(title="Add refresh"))
        assert task.subitems == []

        created = service.add_subitem(task.id, TaskSubItemCreate(title="Added"))

        assert [item.id for item in task.subitems] == [created.id]
        same_session = service.get_task(task.id)
        assert same_session is not None
        assert [item.id for item in same_session.subitems] == [created.id]


def test_delete_subitem_refreshes_loaded_task_and_same_session_get(database_url: str):
    Base.metadata.create_all(bind=get_engine(database_url))
    with session_scope(database_url) as session:
        service = TaskService(session)
        task = service.create_task(
            TaskCreate(
                title="Delete refresh",
                subitems=[TaskSubItemCreate(title="One"), TaskSubItemCreate(title="Two")],
            )
        )
        deleted_id = task.subitems[0].id
        remaining_id = task.subitems[1].id

        service.delete_subitem(task.id, deleted_id)

        assert [item.id for item in task.subitems] == [remaining_id]
        same_session = service.get_task(task.id)
        assert same_session is not None
        assert [item.id for item in same_session.subitems] == [remaining_id]


def test_add_subitem_status_sync_uses_current_subitems(database_url: str):
    Base.metadata.create_all(bind=get_engine(database_url))
    with session_scope(database_url) as session:
        service = TaskService(session)
        task = service.create_task(TaskCreate(title="Status sync", subitems=[TaskSubItemCreate(title="Done")]))
        first_id = task.subitems[0].id
        service.update_subitem(task.id, first_id, TaskSubItemUpdate(status=SubItemStatus.COMPLETED))
        completed = service.get_task(task.id)
        assert completed is not None
        assert completed.status == TaskStatus.COMPLETED

        service.add_subitem(task.id, TaskSubItemCreate(title="Pending"))

        refreshed = service.get_task(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.IN_PROGRESS
        assert {item.status for item in refreshed.subitems} == {SubItemStatus.COMPLETED, SubItemStatus.PENDING}


def test_update_and_reorder_subitems_refresh_loaded_order(database_url: str):
    Base.metadata.create_all(bind=get_engine(database_url))
    with session_scope(database_url) as session:
        service = TaskService(session)
        task = service.create_task(
            TaskCreate(
                title="Order refresh",
                subitems=[TaskSubItemCreate(title="First"), TaskSubItemCreate(title="Second")],
            )
        )
        first_id = task.subitems[0].id
        second_id = task.subitems[1].id

        service.update_subitem(task.id, second_id, TaskSubItemUpdate(sort_order=-1, title="Moved"))

        assert [item.id for item in task.subitems] == [second_id, first_id]
        assert task.subitems[0].title == "Moved"
        requested_order = [item.id for item in reversed(task.subitems)]
        reordered = service.reorder_subitems(task.id, requested_order)
        assert [item.id for item in task.subitems] == requested_order
        assert [item.id for item in reordered.subitems] == requested_order
