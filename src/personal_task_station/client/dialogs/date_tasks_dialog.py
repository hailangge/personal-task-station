from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout

from personal_task_station.shared.enums import TaskStatus
from personal_task_station.shared.schemas import TaskRead


class DateTasksDialog(QDialog):
    createRequested = Signal(date)
    editRequested = Signal(int)
    statusChangeRequested = Signal(int, str)

    def __init__(self, selected_date: date, tasks: list[TaskRead], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Tasks on {selected_date.isoformat()}")
        self.selected_date = selected_date
        self.list_widget = QListWidget()
        for task in tasks:
            item = QListWidgetItem(f"{task.title} [{task.status.value}]")
            item.setToolTip(task.description or task.note)
            item.setData(Qt.ItemDataRole.UserRole, task.id)
            self.list_widget.addItem(item)
        self.list_widget.itemDoubleClicked.connect(self._emit_edit)

        self.add_button = QPushButton("Add task")
        self.add_button.clicked.connect(self._emit_create_and_close)
        self.status_input = QComboBox()
        self.status_input.addItems([status.value for status in TaskStatus])
        self.status_button = QPushButton("Set status")
        self.status_button.clicked.connect(self._emit_status_change)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{len(tasks)} task(s)"))
        layout.addWidget(self.list_widget)
        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.status_input)
        buttons.addWidget(self.status_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def _emit_edit(self, item: QListWidgetItem) -> None:
        task_id = item.data(Qt.ItemDataRole.UserRole)
        if task_id:
            self.editRequested.emit(task_id)

    def _emit_create_and_close(self) -> None:
        self.createRequested.emit(self.selected_date)
        self.close()

    def _emit_status_change(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        if task_id:
            self.statusChangeRequested.emit(task_id, self.status_input.currentText())
