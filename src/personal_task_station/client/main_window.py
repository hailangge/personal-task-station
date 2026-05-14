from __future__ import annotations

from datetime import date

import httpx
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLineEdit,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from personal_task_station.client.api_client import ServerApiClient
from personal_task_station.client.config import ClientSettingsStore
from personal_task_station.client.dialogs.date_tasks_dialog import DateTasksDialog
from personal_task_station.client.dialogs.task_dialog import TaskDialog
from personal_task_station.client.views.connection_view import ConnectionConfigWidget
from personal_task_station.client.views.finance_view import FinanceView
from personal_task_station.client.widgets.calendar_widget import TaskCalendarWidget
from personal_task_station.shared.enums import TaskStatus
from personal_task_station.shared.schemas import ClientSettings, TaskRead, TaskStatusChange


class MainWindow(QMainWindow):
    def __init__(self, api_client: ServerApiClient, settings_store: ClientSettingsStore, settings: ClientSettings):
        super().__init__()
        self.api_client = api_client
        self.settings_store = settings_store
        self.settings = settings
        self.setWindowTitle("Personal Task Station")
        self.resize(1200, 800)

        self.calendar_widget = TaskCalendarWidget()
        self.calendar_widget.mode_selector.setCurrentText(self.settings.desktop.calendar_mode)
        self.calendar_widget.dateActivated.connect(self.open_date_popup)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_all)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(self.settings.desktop.opacity * 100))
        self.opacity_slider.valueChanged.connect(self._apply_opacity)
        self.always_on_top_checkbox = QCheckBox("Always on top")
        self.always_on_top_checkbox.setChecked(self.settings.desktop.always_on_top)
        self.always_on_top_checkbox.toggled.connect(self._apply_window_flags)

        calendar_controls = QHBoxLayout()
        calendar_controls.addWidget(self.refresh_button)
        calendar_controls.addWidget(QLabel("Opacity"))
        calendar_controls.addWidget(self.opacity_slider)
        calendar_controls.addWidget(self.always_on_top_checkbox)
        calendar_controls.addStretch(1)

        calendar_tab = QWidget()
        calendar_layout = QVBoxLayout(calendar_tab)
        calendar_layout.addLayout(calendar_controls)
        calendar_layout.addWidget(self.calendar_widget)

        self.tasks_table = QTableWidget(0, 5)
        self.tasks_table.setHorizontalHeaderLabels(["ID", "Title", "Date", "Status", "Priority"])
        self.tasks_table.cellDoubleClicked.connect(self._edit_table_task)
        self.view_task_button = QPushButton("View details")
        self.view_task_button.clicked.connect(self._view_selected_task)
        self.new_task_button = QPushButton("New task")
        self.new_task_button.clicked.connect(self.open_task_dialog)
        self.delete_task_button = QPushButton("Delete")
        self.delete_task_button.clicked.connect(self._delete_selected_task)
        self.status_change_input = QComboBox()
        self.status_change_input.addItems([status.value for status in TaskStatus])
        self.status_change_button = QPushButton("Set status")
        self.status_change_button.clicked.connect(self._change_selected_task_status)
        self.range_filter = QComboBox()
        self.range_filter.addItems(["all", "today", "this_week", "this_month"])
        self.status_filter = QComboBox()
        self.status_filter.addItem("all")
        self.status_filter.addItems([status.value for status in TaskStatus])
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search title/description/notes")
        self.apply_filter_button = QPushButton("Apply filters")
        self.apply_filter_button.clicked.connect(self.refresh_tasks)
        tasks_tab = QWidget()
        tasks_layout = QVBoxLayout(tasks_tab)
        task_controls = QHBoxLayout()
        task_controls.addWidget(self.new_task_button)
        task_controls.addWidget(self.view_task_button)
        task_controls.addWidget(self.delete_task_button)
        task_controls.addWidget(self.status_change_input)
        task_controls.addWidget(self.status_change_button)
        task_controls.addStretch(1)
        task_filters = QHBoxLayout()
        task_filters.addWidget(QLabel("Range"))
        task_filters.addWidget(self.range_filter)
        task_filters.addWidget(QLabel("Status"))
        task_filters.addWidget(self.status_filter)
        task_filters.addWidget(self.search_input)
        task_filters.addWidget(self.apply_filter_button)
        tasks_layout.addLayout(task_controls)
        tasks_layout.addLayout(task_filters)
        tasks_layout.addWidget(self.tasks_table)

        self.finance_view = FinanceView()
        self.finance_view.load_button.clicked.connect(self.refresh_finance)

        self.connection_view = ConnectionConfigWidget()
        self.connection_view.set_config(self.settings.connection)
        self.connection_view.save_button.clicked.connect(self.save_connection_settings)
        self.connection_view.test_button.clicked.connect(self.test_connection)

        self.tabs = QTabWidget()
        self.tabs.addTab(calendar_tab, "Calendar")
        self.tabs.addTab(tasks_tab, "Tasks")
        self.tabs.addTab(self.finance_view, "Finance")
        self.tabs.addTab(self.connection_view, "Connection")
        self.setCentralWidget(self.tabs)

        self._apply_opacity(self.opacity_slider.value())
        self._apply_window_flags(self.always_on_top_checkbox.isChecked())

    def refresh_all(self) -> None:
        self.refresh_tasks()
        self.refresh_calendar()
        self.refresh_finance()

    def refresh_tasks(self) -> None:
        tasks = self.api_client.list_tasks(**self._task_filter_params())
        self._set_tasks(tasks)

    def refresh_calendar(self) -> None:
        selected = self.calendar_widget.selected_date()
        month_start = date(selected.year, selected.month, 1)
        if selected.month == 12:
            month_end = date(selected.year + 1, 1, 1)
        else:
            month_end = date(selected.year, selected.month + 1, 1)
        month_end = month_end.fromordinal(month_end.toordinal() - 1)
        markers = self.api_client.calendar_summary(month_start, month_end)
        self.calendar_widget.set_markers(markers)

    def refresh_finance(self) -> None:
        selected = self.finance_view.month_selector.date().toPython()
        summary = self.api_client.monthly_summary(selected.year, selected.month)
        transactions = self.api_client.list_transactions(month=selected.strftime("%Y-%m"))
        self.finance_view.set_summary(summary)
        self.finance_view.set_transactions(transactions)

    def open_date_popup(self, selected_date: date) -> None:
        tasks = self.api_client.list_tasks(task_date=selected_date.isoformat())
        dialog = DateTasksDialog(selected_date, tasks, self)
        dialog.createRequested.connect(lambda target_date: self.open_task_dialog(selected_date=target_date))
        dialog.editRequested.connect(self.open_task_dialog_for_id)
        dialog.statusChangeRequested.connect(self._change_task_status_from_date_popup)
        dialog.exec()

    def open_task_dialog(self, selected_date: date | None = None) -> None:
        dialog = TaskDialog(self)
        if selected_date:
            dialog.task_date_input.setDate(QDate(selected_date.year, selected_date.month, selected_date.day))
        if dialog.exec():
            try:
                payload = dialog.create_payload()
            except ValueError as exc:
                QMessageBox.warning(self, "Task", str(exc))
                return
            self.api_client.create_task(payload)
            self.refresh_all()

    def open_task_dialog_for_id(self, task_id: int) -> None:
        task = self.api_client.get_task(task_id)
        dialog = TaskDialog(self, task=task, api_client=self.api_client)
        if dialog.exec():
            try:
                payload = dialog.update_payload()
            except ValueError as exc:
                QMessageBox.warning(self, "Task", str(exc))
                return
            self.api_client.update_task(task_id, payload)
            self.refresh_all()

    def save_connection_settings(self) -> None:
        self.settings = self.settings.model_copy(update={"connection": self.connection_view.get_config()})
        self.settings_store.save(self.settings)
        self.connection_view.status_label.setText("Saved configuration.")

    def test_connection(self) -> None:
        try:
            config = self.connection_view.get_config()
            client = self.api_client.__class__(config, transport=getattr(self.api_client, "_transport", None))
            status = client.health()
            self.connection_view.status_label.setText(f"Connected: {status['status']}")
        except Exception as exc:
            self.connection_view.status_label.setText(f"Connection failed: {exc}")

    def _set_tasks(self, tasks: list[TaskRead]) -> None:
        self.tasks_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self.tasks_table.setItem(row, 0, QTableWidgetItem(str(task.id)))
            self.tasks_table.setItem(row, 1, QTableWidgetItem(task.title))
            self.tasks_table.setItem(row, 2, QTableWidgetItem(task.task_date.isoformat() if task.task_date else ""))
            self.tasks_table.setItem(row, 3, QTableWidgetItem(task.status.value))
            self.tasks_table.setItem(row, 4, QTableWidgetItem(str(task.priority)))

    def _edit_table_task(self, row: int, _column: int) -> None:
        item = self.tasks_table.item(row, 0)
        if item:
            self.open_task_dialog_for_id(int(item.text()))

    def _view_selected_task(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self.open_task_dialog_for_id(task_id)

    def _delete_selected_task(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self.api_client.delete_task(task_id)
            self.refresh_all()

    def _change_selected_task_status(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self.api_client.change_task_status(
                task_id,
                TaskStatusChange(status=TaskStatus(self.status_change_input.currentText()), reason="Changed from desktop UI", source="client"),
            )
            self.refresh_all()

    def _change_task_status_from_date_popup(self, task_id: int, status_value: str) -> None:
        self.api_client.change_task_status(
            task_id,
            TaskStatusChange(status=TaskStatus(status_value), reason="Changed from calendar popup", source="client"),
        )
        self.refresh_all()

    def _selected_task_id(self) -> int | None:
        selected = self.tasks_table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        item = self.tasks_table.item(row, 0)
        return int(item.text()) if item else None

    def _task_filter_params(self) -> dict:
        params: dict = {}
        today = date.today()
        selected_range = self.range_filter.currentText()
        if selected_range == "today":
            params["task_date"] = today.isoformat()
        elif selected_range == "this_week":
            start = today.fromordinal(today.toordinal() - today.weekday())
            params["start_date"] = start.isoformat()
            params["end_date"] = start.fromordinal(start.toordinal() + 6).isoformat()
        elif selected_range == "this_month":
            start = date(today.year, today.month, 1)
            if today.month == 12:
                end = date(today.year + 1, 1, 1)
            else:
                end = date(today.year, today.month + 1, 1)
            params["start_date"] = start.isoformat()
            params["end_date"] = end.fromordinal(end.toordinal() - 1).isoformat()
        if self.status_filter.currentText() != "all":
            params["status"] = self.status_filter.currentText()
        query = self.search_input.text().strip()
        if query:
            params["query"] = query
        return params

    def _apply_opacity(self, value: int) -> None:
        opacity = value / 100
        self.setWindowOpacity(opacity)
        self.settings = self.settings.model_copy(update={"desktop": self.settings.desktop.model_copy(update={"opacity": opacity})})
        self.settings_store.save(self.settings)

    def _apply_window_flags(self, checked: bool) -> None:
        self.settings = self.settings.model_copy(
            update={"desktop": self.settings.desktop.model_copy(update={"always_on_top": checked})}
        )
        self.settings_store.save(self.settings)
        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
