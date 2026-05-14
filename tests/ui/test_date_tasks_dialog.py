from __future__ import annotations

from datetime import date

from personal_task_station.client.dialogs.date_tasks_dialog import DateTasksDialog
from personal_task_station.shared.schemas import TaskRead


def test_date_tasks_dialog_emits_status_change(qtbot):
    task = TaskRead.model_validate(
        {
            "id": 1,
            "title": "Daily task",
            "description": "",
            "task_date": "2026-05-14",
            "start_at": None,
            "due_at": None,
            "status": "scheduled",
            "priority": 3,
            "tags": [],
            "is_pinned": False,
            "note": "",
            "created_at": "2026-05-14T00:00:00",
            "updated_at": "2026-05-14T00:00:00",
            "subitems": [],
            "history": [],
        }
    )
    dialog = DateTasksDialog(date(2026, 5, 14), [task])
    qtbot.addWidget(dialog)
    dialog.list_widget.setCurrentRow(0)
    dialog.status_input.setCurrentText("completed")

    with qtbot.waitSignal(dialog.statusChangeRequested) as blocker:
        dialog.status_button.click()

    assert blocker.args == [1, "completed"]
