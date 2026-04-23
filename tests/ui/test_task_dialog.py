from __future__ import annotations

from personal_task_station.client.dialogs.task_dialog import TaskDialog


def test_task_dialog_creates_payload(qtbot):
    dialog = TaskDialog()
    qtbot.addWidget(dialog)
    dialog.title_input.setText("Draft summary")
    dialog.description_input.setPlainText("Prepare validation notes")
    payload = dialog.create_payload()
    assert payload.title == "Draft summary"
    assert payload.description == "Prepare validation notes"
