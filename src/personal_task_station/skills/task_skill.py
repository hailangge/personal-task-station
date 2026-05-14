from __future__ import annotations

import argparse
import json
from datetime import date

from personal_task_station.shared.enums import TaskStatus
from personal_task_station.shared.schemas import TaskCreate, TaskStatusChange, TaskSubItemCreate, TaskUpdate
from personal_task_station.skills.base import build_skill_client


class TaskSkill:
    def __init__(self):
        self.client = build_skill_client()

    def tasks_for_day(self, target_date: date) -> list[dict]:
        return [task.model_dump(mode="json") for task in self.client.list_tasks(task_date=target_date.isoformat())]

    def task_detail(self, task_id: int) -> dict:
        return self.client.get_task(task_id).model_dump(mode="json")

    def create_task(self, **kwargs) -> dict:
        payload = TaskCreate(**kwargs)
        return self.client.create_task(payload).model_dump(mode="json")

    def update_task(self, task_id: int, **kwargs) -> dict:
        payload = TaskUpdate(**kwargs)
        return self.client.update_task(task_id, payload).model_dump(mode="json")

    def update_status(self, task_id: int, status: str, reason: str = "", source: str = "skill") -> dict:
        payload = TaskStatusChange(status=TaskStatus(status), reason=reason, source=source)
        return self.client.change_task_status(task_id, payload).model_dump(mode="json")

    def add_subitem(self, task_id: int, title: str, description: str = "") -> dict:
        payload = TaskSubItemCreate(title=title, description=description)
        return self.client.add_subitem(task_id, payload).model_dump(mode="json")

    def delete_task(self, task_id: int) -> dict:
        self.client.delete_task(task_id)
        return {"deleted": task_id}

    def reorder_subitems(self, task_id: int, ordered_ids: list[int]) -> dict:
        return self.client.reorder_subitems(task_id, ordered_ids).model_dump(mode="json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Task skill wrapper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-day")
    list_parser.add_argument("--date", required=True)

    detail_parser = subparsers.add_parser("detail")
    detail_parser.add_argument("--task-id", type=int, required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--title", required=True)
    create_parser.add_argument("--description", default="")
    create_parser.add_argument("--task-date")
    create_parser.add_argument("--priority", type=int, default=3)

    update_parser = subparsers.add_parser("update")
    update_parser.add_argument("--task-id", type=int, required=True)
    update_parser.add_argument("--title")
    update_parser.add_argument("--description")
    update_parser.add_argument("--note")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--task-id", type=int, required=True)
    status_parser.add_argument("--status", required=True)
    status_parser.add_argument("--reason", default="")

    subitem_parser = subparsers.add_parser("add-subitem")
    subitem_parser.add_argument("--task-id", type=int, required=True)
    subitem_parser.add_argument("--title", required=True)
    subitem_parser.add_argument("--description", default="")

    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("--task-id", type=int, required=True)

    reorder_parser = subparsers.add_parser("reorder-subitems")
    reorder_parser.add_argument("--task-id", type=int, required=True)
    reorder_parser.add_argument("--ids", type=int, nargs="+", required=True)

    args = parser.parse_args()
    skill = TaskSkill()
    if args.command == "list-day":
        result = skill.tasks_for_day(date.fromisoformat(args.date))
    elif args.command == "detail":
        result = skill.task_detail(args.task_id)
    elif args.command == "create":
        payload = {
            "title": args.title,
            "description": args.description,
            "priority": args.priority,
        }
        if args.task_date:
            payload["task_date"] = args.task_date
        result = skill.create_task(**payload)
    elif args.command == "update":
        payload = {key: value for key, value in {"title": args.title, "description": args.description, "note": args.note}.items() if value is not None}
        result = skill.update_task(args.task_id, **payload)
    elif args.command == "status":
        result = skill.update_status(args.task_id, args.status, args.reason)
    elif args.command == "add-subitem":
        result = skill.add_subitem(args.task_id, args.title, args.description)
    elif args.command == "delete":
        result = skill.delete_task(args.task_id)
    else:
        result = skill.reorder_subitems(args.task_id, args.ids)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
