from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from personal_task_station.server.dependencies import get_db
from personal_task_station.server.services.tasks import TaskService
from personal_task_station.shared.enums import TaskStatus
from personal_task_station.shared.schemas import (
    CalendarDaySummary,
    TaskCreate,
    TaskRead,
    TaskStatusChange,
    TaskStatusHistoryRead,
    TaskSubItemCreate,
    TaskSubItemRead,
    TaskSubItemUpdate,
    TaskUpdate,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _service(session: Session) -> TaskService:
    return TaskService(session)


@router.get("", response_model=list[TaskRead])
def list_tasks(
    task_date: date | None = None,
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    query: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    session: Session = Depends(get_db),
) -> list[TaskRead]:
    return _service(session).list_tasks(
        task_date=task_date,
        status=status_filter,
        query=query,
        start_date=start_date,
        end_date=end_date,
    )


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, session: Session = Depends(get_db)) -> TaskRead:
    return _service(session).create_task(payload)


@router.get("/calendar/summary", response_model=list[CalendarDaySummary])
def calendar_summary(
    start_date: date,
    end_date: date,
    session: Session = Depends(get_db),
) -> list[CalendarDaySummary]:
    return _service(session).calendar_summary(start_date, end_date)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, session: Session = Depends(get_db)) -> TaskRead:
    task = _service(session).get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=TaskRead)
@router.patch("/{task_id}", response_model=TaskRead)
def update_task(task_id: int, payload: TaskUpdate, session: Session = Depends(get_db)) -> TaskRead:
    try:
        return _service(session).update_task(task_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, session: Session = Depends(get_db)) -> None:
    try:
        _service(session).delete_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{task_id}/status", response_model=TaskRead)
def change_status(task_id: int, payload: TaskStatusChange, session: Session = Depends(get_db)) -> TaskRead:
    try:
        return _service(session).change_status(task_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{task_id}/history", response_model=list[TaskStatusHistoryRead])
def task_history(task_id: int, session: Session = Depends(get_db)) -> list[TaskStatusHistoryRead]:
    try:
        return _service(session).get_history(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{task_id}/subitems", response_model=TaskSubItemRead, status_code=status.HTTP_201_CREATED)
def add_subitem(task_id: int, payload: TaskSubItemCreate, session: Session = Depends(get_db)) -> TaskSubItemRead:
    try:
        return _service(session).add_subitem(task_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{task_id}/subitems/{subitem_id}", response_model=TaskSubItemRead)
@router.patch("/{task_id}/subitems/{subitem_id}", response_model=TaskSubItemRead)
def update_subitem(
    task_id: int,
    subitem_id: int,
    payload: TaskSubItemUpdate,
    session: Session = Depends(get_db),
) -> TaskSubItemRead:
    try:
        return _service(session).update_subitem(task_id, subitem_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{task_id}/subitems/{subitem_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subitem(task_id: int, subitem_id: int, session: Session = Depends(get_db)) -> None:
    try:
        _service(session).delete_subitem(task_id, subitem_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{task_id}/subitems/reorder", response_model=TaskRead)
def reorder_subitems(task_id: int, ordered_ids: list[int], session: Session = Depends(get_db)) -> TaskRead:
    try:
        return _service(session).reorder_subitems(task_id, ordered_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
