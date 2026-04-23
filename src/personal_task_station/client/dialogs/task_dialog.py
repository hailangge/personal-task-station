from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, QDateTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from personal_task_station.shared.enums import TaskStatus
from personal_task_station.shared.schemas import TaskCreate, TaskRead, TaskUpdate


class TaskDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, task: TaskRead | None = None):
        super().__init__(parent)
        self.setWindowTitle("Task")
        self._task = task

        self.title_input = QLineEdit()
        self.description_input = QPlainTextEdit()
        self.task_date_enabled = QCheckBox("Set date")
        self.task_date_enabled.setChecked(True)
        self.task_date_input = QDateEdit()
        self.task_date_input.setCalendarPopup(True)
        self.task_date_input.setDate(QDate.currentDate())
        self.task_date_enabled.toggled.connect(self.task_date_input.setEnabled)

        self.start_enabled = QCheckBox("Start time")
        self.start_input = QDateTimeEdit()
        self.start_input.setCalendarPopup(True)
        self.start_input.setDateTime(QDateTime.currentDateTime())

        self.due_enabled = QCheckBox("Due time")
        self.due_input = QDateTimeEdit()
        self.due_input.setCalendarPopup(True)
        self.due_input.setDateTime(QDateTime.currentDateTime())

        self.status_input = QComboBox()
        self.status_input.addItems([status.value for status in TaskStatus])

        self.priority_input = QSpinBox()
        self.priority_input.setRange(1, 5)
        self.priority_input.setValue(3)

        self.tags_input = QLineEdit()
        self.pinned_input = QCheckBox("Pinned")
        self.note_input = QPlainTextEdit()

        form = QFormLayout()
        form.addRow("Title", self.title_input)
        form.addRow("Description", self.description_input)
        form.addRow(self.task_date_enabled, self.task_date_input)
        form.addRow(self.start_enabled, self.start_input)
        form.addRow(self.due_enabled, self.due_input)
        form.addRow("Status", self.status_input)
        form.addRow("Priority", self.priority_input)
        form.addRow("Tags", self.tags_input)
        form.addRow("", self.pinned_input)
        form.addRow("Note", self.note_input)

        self.history_group = QGroupBox("Status history")
        self.history_list = QListWidget()
        history_layout = QVBoxLayout(self.history_group)
        history_layout.addWidget(self.history_list)
        self.history_group.setVisible(False)

        self.subitems_group = QGroupBox("Subitems")
        self.subitems_list = QListWidget()
        subitems_layout = QVBoxLayout(self.subitems_group)
        subitems_layout.addWidget(self.subitems_list)
        self.subitems_group.setVisible(False)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.subitems_group)
        layout.addWidget(self.history_group)
        layout.addWidget(buttons)

        if task:
            self.populate(task)

    def populate(self, task: TaskRead) -> None:
        self.title_input.setText(task.title)
        self.description_input.setPlainText(task.description)
        if task.task_date:
            self.task_date_enabled.setChecked(True)
            self.task_date_input.setDate(QDate(task.task_date.year, task.task_date.month, task.task_date.day))
        else:
            self.task_date_enabled.setChecked(False)
        if task.start_at:
            self.start_enabled.setChecked(True)
            self.start_input.setDateTime(QDateTime.fromString(task.start_at.isoformat(), Qt.DateFormat.ISODate))
        if task.due_at:
            self.due_enabled.setChecked(True)
            self.due_input.setDateTime(QDateTime.fromString(task.due_at.isoformat(), Qt.DateFormat.ISODate))
        self.status_input.setCurrentText(task.status.value)
        self.priority_input.setValue(task.priority)
        self.tags_input.setText(", ".join(task.tags))
        self.pinned_input.setChecked(task.is_pinned)
        self.note_input.setPlainText(task.note)
        self.subitems_list.clear()
        for sub in task.subitems:
            self.subitems_list.addItem(f"{'[x] ' if sub.completed else '[ ] '}{sub.title} ({sub.status.value})")
        self.subitems_group.setVisible(bool(task.subitems))
        self.history_list.clear()
        for entry in task.history:
            old = entry.old_status.value if entry.old_status else "—"
            self.history_list.addItem(f"{entry.changed_at.strftime('%Y-%m-%d %H:%M')}  {old} → {entry.new_status.value}  ({entry.source})")
        self.history_group.setVisible(bool(task.history))

    def create_payload(self) -> TaskCreate:
        return TaskCreate(**self._payload())

    def update_payload(self) -> TaskUpdate:
        return TaskUpdate(**self._payload())

    def _payload(self) -> dict:
        title = self.title_input.text().strip()
        if not title:
            raise ValueError("Title is required.")
        task_date = self.task_date_input.date().toPython() if self.task_date_enabled.isChecked() else None
        start_at = self.start_input.dateTime().toPython() if self.start_enabled.isChecked() else None
        due_at = self.due_input.dateTime().toPython() if self.due_enabled.isChecked() else None
        return {
            "title": title,
            "description": self.description_input.toPlainText().strip(),
            "task_date": task_date,
            "start_at": self._normalize_datetime(start_at),
            "due_at": self._normalize_datetime(due_at),
            "status": TaskStatus(self.status_input.currentText()),
            "priority": self.priority_input.value(),
            "tags": [item.strip() for item in self.tags_input.text().split(",") if item.strip()],
            "is_pinned": self.pinned_input.isChecked(),
            "note": self.note_input.toPlainText().strip(),
        }

    def _normalize_datetime(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(microsecond=0)
