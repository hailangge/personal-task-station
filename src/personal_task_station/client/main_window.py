from __future__ import annotations

from datetime import date

import httpx
from PySide6.QtCore import QDate, QEvent, QPoint, Qt
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QMenu,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QSizeGrip,
    QMessageBox,
    QPushButton,
    QSlider,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QToolButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
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
    DEFAULT_WINDOW_SIZE = (920, 620)
    WINDOW_MARGIN = 24
    SNAP_DISTANCE = 28

    def __init__(self, api_client: ServerApiClient, settings_store: ClientSettingsStore, settings: ClientSettings):
        super().__init__()
        self.api_client = api_client
        self.settings_store = settings_store
        self.settings = settings
        self._drag_offset: QPoint | None = None
        self._position_restored = False
        self._quit_requested = False
        self.setWindowTitle("Personal Task Station")
        self.resize(*self.DEFAULT_WINDOW_SIZE)
        self.setMinimumSize(520, 360)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self.container = QFrame()
        self.container.setObjectName("floatingContainer")
        self.container.installEventFilter(self)
        self._apply_theme_styles()
        shadow = QGraphicsDropShadowEffect(self.container)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.container.setGraphicsEffect(shadow)

        self.calendar_widget = TaskCalendarWidget()
        self.calendar_widget.set_background_color(self.settings.desktop.calendar_background_color)
        self.calendar_widget.set_border_color(self.settings.desktop.calendar_border_color)
        self.calendar_widget.set_header_color(self.settings.desktop.calendar_header_color)
        self.calendar_widget.mode_selector.setCurrentText(self.settings.desktop.calendar_mode)
        self.calendar_widget.mode_selector.currentTextChanged.connect(self._persist_calendar_mode)
        self.calendar_widget.dateActivated.connect(self.open_date_popup)

        self.refresh_button = QToolButton()
        self.refresh_button.setText("↻")
        self.refresh_button.setToolTip("Refresh")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh_all)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(self.settings.desktop.opacity * 100))
        self.opacity_slider.valueChanged.connect(self._apply_opacity)
        self.always_on_top_checkbox = QCheckBox("Always on top")
        self.always_on_top_checkbox.setChecked(self.settings.desktop.always_on_top)
        self.always_on_top_checkbox.toggled.connect(self._apply_window_flags)

        self.utility_menu = self._build_utility_menu()
        self.utility_button = QToolButton()
        self.utility_button.setText("⋯")
        self.utility_button.setToolTip("Window and calendar controls")
        self.utility_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.utility_button.setMenu(self.utility_menu)
        self.utility_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_theme_styles()

        self.hide_button = QToolButton()
        self.hide_button.setText("—")
        self.hide_button.setToolTip("Hide to tray")
        self.hide_button.clicked.connect(self.hide)
        self.hide_button.setCursor(Qt.CursorShape.PointingHandCursor)

        calendar_tab = QWidget()
        calendar_layout = QVBoxLayout(calendar_tab)
        calendar_layout.setContentsMargins(8, 8, 8, 8)
        self.calendar_widget.header_widget.hide()
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
        tasks_layout.setContentsMargins(8, 8, 8, 8)
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
        self.finance_view.import_button.clicked.connect(self.import_finance_csv)
        self.finance_view.reanalyze_button.clicked.connect(self.reanalyze_finance)
        self.finance_view.undo_duplicate_button.clicked.connect(self.undo_selected_duplicate)

        self.connection_view = ConnectionConfigWidget()
        self.connection_view.set_config(self.settings.connection)
        self.connection_view.save_button.clicked.connect(self.save_connection_settings)
        self.connection_view.test_button.clicked.connect(self.test_connection)

        self.tabs = QTabWidget()
        self.tabs.addTab(calendar_tab, "Calendar")
        self.tabs.addTab(tasks_tab, "Tasks")
        self.tabs.addTab(self.finance_view, "Finance")
        self.tabs.addTab(self.connection_view, "Connection")
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: none; background: transparent; }"
            "QTabBar::tab { background: rgba(255,255,255,0.08); color: white; padding: 6px 12px; border-radius: 10px; margin-right: 6px; }"
            "QTabBar::tab:selected { background: rgba(255,255,255,0.18); }"
        )

        self.drag_handle = QLabel("Personal Task Station")
        self.drag_handle.setCursor(Qt.CursorShape.SizeAllCursor)
        self.drag_handle.setStyleSheet("color: rgba(255, 255, 255, 210); font-weight: 600; padding-left: 4px;")
        self.drag_handle.installEventFilter(self)

        self.size_grip = QSizeGrip(self.container)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.addWidget(self.drag_handle, 1)
        top_bar.addWidget(self.refresh_button)
        top_bar.addWidget(self.utility_button)
        top_bar.addWidget(self.hide_button)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(14, 14, 14, 14)
        container_layout.setSpacing(10)
        container_layout.addLayout(top_bar)
        container_layout.addWidget(self.tabs)
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch(1)
        grip_row.addWidget(self.size_grip)
        container_layout.addLayout(grip_row)
        self.setCentralWidget(self.container)

        self._setup_tray_icon()

        self._apply_opacity(self.opacity_slider.value())
        self._apply_window_flags(self.always_on_top_checkbox.isChecked())
        self._restore_or_place_window()

    def eventFilter(self, watched, event) -> bool:
        is_drag_surface = watched is self.container or watched is self.drag_handle
        if is_drag_surface and event.type() == QEvent.Type.MouseButtonPress:
            return self._start_drag(event)
        if is_drag_surface and event.type() == QEvent.Type.MouseMove:
            return self._move_drag(event)
        if is_drag_surface and event.type() == QEvent.Type.MouseButtonRelease:
            return self._finish_drag(event)
        return super().eventFilter(watched, event)

    def closeEvent(self, event) -> None:
        if self._quit_requested:
            super().closeEvent(event)
            return
        event.ignore()
        self.hide()

    def _build_utility_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("windowUtilityMenu")

        view_mode_menu = QMenu("View mode", menu)
        for mode in ("month", "week", "compact"):
            action = QAction(mode.title(), view_mode_menu)
            action.setCheckable(True)
            action.setChecked(self.calendar_widget.mode_selector.currentText() == mode)
            action.triggered.connect(lambda _checked=False, selected_mode=mode: self.calendar_widget.mode_selector.setCurrentText(selected_mode))
            self.calendar_widget.mode_selector.currentTextChanged.connect(
                lambda current_mode, menu_action=action, selected_mode=mode: menu_action.setChecked(current_mode == selected_mode)
            )
            view_mode_menu.addAction(action)
        menu.addMenu(view_mode_menu)

        self.always_on_top_action = QAction("Always on top", menu)
        self.always_on_top_action.setCheckable(True)
        self.always_on_top_action.setChecked(self.settings.desktop.always_on_top)
        self.always_on_top_action.toggled.connect(self.always_on_top_checkbox.setChecked)
        self.always_on_top_checkbox.toggled.connect(self.always_on_top_action.setChecked)
        menu.addAction(self.always_on_top_action)

        appearance_menu = QMenu("Appearance", menu)
        self.background_color_action = QAction("Main background color…", appearance_menu)
        self.background_color_action.triggered.connect(self._choose_background_color)
        appearance_menu.addAction(self.background_color_action)
        self.calendar_background_color_action = QAction("Calendar background color…", appearance_menu)
        self.calendar_background_color_action.triggered.connect(self._choose_calendar_background_color)
        appearance_menu.addAction(self.calendar_background_color_action)
        self.calendar_border_color_action = QAction("Calendar border color…", appearance_menu)
        self.calendar_border_color_action.triggered.connect(self._choose_calendar_border_color)
        appearance_menu.addAction(self.calendar_border_color_action)
        self.calendar_header_color_action = QAction("Calendar header color…", appearance_menu)
        self.calendar_header_color_action.triggered.connect(self._choose_calendar_header_color)
        appearance_menu.addAction(self.calendar_header_color_action)
        menu.addMenu(appearance_menu)

        opacity_action = QWidgetAction(menu)
        opacity_panel = QWidget(menu)
        opacity_layout = QHBoxLayout(opacity_panel)
        opacity_layout.setContentsMargins(12, 6, 12, 6)
        opacity_label = QLabel("Opacity")
        opacity_label.setStyleSheet("color: white;")
        self.opacity_slider.setFixedWidth(120)
        opacity_layout.addWidget(opacity_label)
        opacity_layout.addWidget(self.opacity_slider)
        opacity_action.setDefaultWidget(opacity_panel)
        menu.addAction(opacity_action)

        refresh_action = QAction("Refresh now", menu)
        refresh_action.triggered.connect(self.refresh_all)
        menu.addAction(refresh_action)

        menu.addSeparator()
        show_action = QAction("Show window", menu)
        show_action.triggered.connect(self.show_window)
        menu.addAction(show_action)
        hide_action = QAction("Hide to tray", menu)
        hide_action.triggered.connect(self.hide)
        menu.addAction(hide_action)
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit_from_tray)
        menu.addAction(quit_action)
        return menu

    def _setup_tray_icon(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        if icon.isNull():
            icon = QIcon()
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Personal Task Station")
        tray_menu = QMenu(self)
        tray_menu.addAction("Show", self.show_window)
        tray_menu.addAction("Hide", self.hide)
        tray_menu.addSeparator()
        tray_menu.addAction("Quit", self.quit_from_tray)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._handle_tray_activation)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()

    def _handle_tray_activation(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_from_tray(self) -> None:
        self._quit_requested = True
        self.tray_icon.hide()
        QApplication.quit()

    def _apply_theme_styles(self) -> None:
        background = self._rgba_from_hex(self.settings.desktop.main_background_color, 188)
        menu_background = self._rgba_from_hex(self.settings.desktop.main_background_color, 242)
        self.container.setStyleSheet(
            "#floatingContainer {"
            f"background-color: {background};"
            "border: 1px solid rgba(255, 255, 255, 32);"
            "border-radius: 18px;"
            "}"
        )
        if hasattr(self, "utility_menu"):
            self.utility_menu.setStyleSheet(
                "QMenu {"
                f"background: {menu_background};"
                "color: white; border: 1px solid rgba(255,255,255,0.16); border-radius: 10px;"
                "}"
                "QMenu::item { padding: 6px 18px; }"
                "QMenu::item:selected { background: rgba(93,173,226,0.35); }"
            )

    def _choose_background_color(self) -> None:
        selected = QColorDialog.getColor(
            QColor(self.settings.desktop.main_background_color),
            self,
            "Main background color",
        )
        if selected.isValid():
            self._set_main_background_color(selected.name())

    def _choose_calendar_background_color(self) -> None:
        selected = QColorDialog.getColor(
            QColor(self.settings.desktop.calendar_background_color),
            self,
            "Calendar background color",
        )
        if selected.isValid():
            self._set_calendar_background_color(selected.name())

    def _choose_calendar_border_color(self) -> None:
        selected = QColorDialog.getColor(
            QColor(self.settings.desktop.calendar_border_color),
            self,
            "Calendar border color",
        )
        if selected.isValid():
            self._set_calendar_border_color(selected.name())

    def _choose_calendar_header_color(self) -> None:
        selected = QColorDialog.getColor(
            QColor(self.settings.desktop.calendar_header_color),
            self,
            "Calendar header color",
        )
        if selected.isValid():
            self._set_calendar_header_color(selected.name())

    def _set_main_background_color(self, color: str) -> None:
        selected = QColor(color)
        if not selected.isValid():
            return
        normalized = selected.name()
        desktop = self.settings.desktop
        if desktop.main_background_color == normalized:
            return
        self.settings = self.settings.model_copy(
            update={"desktop": desktop.model_copy(update={"main_background_color": normalized})}
        )
        self._apply_theme_styles()
        self.settings_store.save(self.settings)

    def _set_calendar_background_color(self, color: str) -> None:
        selected = QColor(color)
        if not selected.isValid():
            return
        normalized = selected.name()
        desktop = self.settings.desktop
        if desktop.calendar_background_color == normalized:
            return
        self.settings = self.settings.model_copy(
            update={"desktop": desktop.model_copy(update={"calendar_background_color": normalized})}
        )
        self.calendar_widget.set_background_color(normalized)
        self.settings_store.save(self.settings)

    def _set_calendar_border_color(self, color: str) -> None:
        selected = QColor(color)
        if not selected.isValid():
            return
        normalized = selected.name()
        desktop = self.settings.desktop
        if desktop.calendar_border_color == normalized:
            return
        self.settings = self.settings.model_copy(
            update={"desktop": desktop.model_copy(update={"calendar_border_color": normalized})}
        )
        self.calendar_widget.set_border_color(normalized)
        self.settings_store.save(self.settings)

    def _set_calendar_header_color(self, color: str) -> None:
        selected = QColor(color)
        if not selected.isValid():
            return
        normalized = selected.name()
        desktop = self.settings.desktop
        if desktop.calendar_header_color == normalized:
            return
        self.settings = self.settings.model_copy(
            update={"desktop": desktop.model_copy(update={"calendar_header_color": normalized})}
        )
        self.calendar_widget.set_header_color(normalized)
        self.settings_store.save(self.settings)

    @staticmethod
    def _rgba_from_hex(color: str, alpha: int) -> str:
        selected = QColor(color)
        if not selected.isValid():
            selected = QColor("#334155")
        return f"rgba({selected.red()}, {selected.green()}, {selected.blue()}, {alpha})"

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
        self.finance_view.set_duplicates(summary.duplicates)

    def import_finance_csv(self) -> None:
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import transaction CSV",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not file_path:
            return
        source_name = self.finance_view.source_input.text().strip() or "csv"
        try:
            job = self.api_client.import_billing_file(source_name, file_path)
        except Exception as exc:
            QMessageBox.warning(self, "Finance import", f"Import failed: {exc}")
            self.finance_view.status_label.setText(f"Import failed: {exc}")
            return
        self.finance_view.status_label.setText(
            f"Imported {job.normalized_count} transactions from {job.filename}; detected {job.merged_count} merged groups."
        )
        self.refresh_finance()

    def reanalyze_finance(self) -> None:
        try:
            self.api_client.reanalyze()
        except Exception as exc:
            QMessageBox.warning(self, "Finance", f"Reanalyze failed: {exc}")
            self.finance_view.status_label.setText(f"Reanalyze failed: {exc}")
            return
        self.finance_view.status_label.setText("Reanalyzed transaction categories and duplicate groups.")
        self.refresh_finance()

    def undo_selected_duplicate(self) -> None:
        duplicate_id = self.finance_view.selected_duplicate_id()
        if duplicate_id is None:
            self.finance_view.status_label.setText("Select a duplicate row before undoing a merge.")
            return
        try:
            self.api_client.undo_merge(duplicate_id)
        except Exception as exc:
            QMessageBox.warning(self, "Finance", f"Undo failed: {exc}")
            self.finance_view.status_label.setText(f"Undo failed: {exc}")
            return
        self.finance_view.status_label.setText(f"Undid duplicate merge {duplicate_id}.")
        self.refresh_finance()

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
        current_position = self.pos()
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if checked:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        if self._position_restored:
            self.move(current_position)

    def mousePressEvent(self, event) -> None:
        if self._start_drag(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._move_drag(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._finish_drag(event):
            return
        super().mouseReleaseEvent(event)

    def _start_drag(self, event) -> bool:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return True
        return False

    def _move_drag(self, event) -> bool:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return True
        return False

    def _finish_drag(self, event) -> bool:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self._snap_to_screen_edges()
            self._persist_window_position()
            event.accept()
            return True
        return False

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self.isVisible():
            self._persist_window_position()

    def _restore_or_place_window(self) -> None:
        desktop = self.settings.desktop
        if desktop.window_x is not None and desktop.window_y is not None:
            self.move(desktop.window_x, desktop.window_y)
        else:
            self.move(self._default_top_right_position())
        self._position_restored = True

    def _default_top_right_position(self) -> QPoint:
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else self.geometry()
        x = max(available.x() + self.WINDOW_MARGIN, available.right() - self.width() - self.WINDOW_MARGIN)
        y = available.y() + self.WINDOW_MARGIN
        return QPoint(x, y)

    def _persist_window_position(self) -> None:
        desktop = self.settings.desktop
        if desktop.window_x == self.x() and desktop.window_y == self.y():
            return
        self.settings = self.settings.model_copy(
            update={
                "desktop": desktop.model_copy(
                    update={
                        "window_x": self.x(),
                        "window_y": self.y(),
                    }
                )
            }
        )
        self.settings_store.save(self.settings)

    def _snap_to_screen_edges(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        target_x = self.x()
        target_y = self.y()
        left = available.left() + self.WINDOW_MARGIN
        top = available.top() + self.WINDOW_MARGIN
        right = available.right() - self.width() - self.WINDOW_MARGIN
        bottom = available.bottom() - self.height() - self.WINDOW_MARGIN
        if abs(self.x() - left) <= self.SNAP_DISTANCE:
            target_x = left
        elif abs(self.x() - right) <= self.SNAP_DISTANCE:
            target_x = right
        if abs(self.y() - top) <= self.SNAP_DISTANCE:
            target_y = top
        elif abs(self.y() - bottom) <= self.SNAP_DISTANCE:
            target_y = bottom
        if target_x != self.x() or target_y != self.y():
            self.move(target_x, target_y)

    def _persist_calendar_mode(self, mode: str) -> None:
        desktop = self.settings.desktop
        if desktop.calendar_mode == mode:
            return
        self.settings = self.settings.model_copy(update={"desktop": desktop.model_copy(update={"calendar_mode": mode})})
        self.settings_store.save(self.settings)
