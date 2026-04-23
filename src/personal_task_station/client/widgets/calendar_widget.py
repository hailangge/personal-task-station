from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from personal_task_station.shared.enums import TaskStatus
from personal_task_station.shared.schemas import CalendarDaySummary


class TaskCalendarWidget(QWidget):
    dateActivated = Signal(date)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.markers: dict[date, CalendarDaySummary] = {}

        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["month", "week", "compact"])
        self.mode_selector.currentTextChanged.connect(self._switch_mode)

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.clicked.connect(self._emit_calendar_date)

        self.week_list = QListWidget()
        self.week_list.itemActivated.connect(self._emit_list_item_date)
        self.week_list.itemClicked.connect(self._emit_list_item_date)

        self.compact_list = QListWidget()
        self.compact_list.itemActivated.connect(self._emit_list_item_date)
        self.compact_list.itemClicked.connect(self._emit_list_item_date)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.calendar)
        self.stack.addWidget(self.week_list)
        self.stack.addWidget(self.compact_list)

        header = QHBoxLayout()
        header.addWidget(QLabel("Calendar style"))
        header.addWidget(self.mode_selector)
        header.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.stack)
        self._switch_mode("month")

    def set_markers(self, markers: list[CalendarDaySummary]) -> None:
        self.markers = {item.date: item for item in markers}
        self._apply_calendar_formats()
        self._refresh_week_view()
        self._refresh_compact_view()

    def selected_date(self) -> date:
        qdate = self.calendar.selectedDate()
        return date(qdate.year(), qdate.month(), qdate.day())

    def set_selected_date(self, selected: date) -> None:
        qdate = QDate(selected.year, selected.month, selected.day)
        self.calendar.setSelectedDate(qdate)
        self._refresh_week_view()

    def marker_for(self, selected: date) -> CalendarDaySummary | None:
        return self.markers.get(selected)

    def _switch_mode(self, mode: str) -> None:
        index = {"month": 0, "week": 1, "compact": 2}[mode]
        self.stack.setCurrentIndex(index)
        self._refresh_week_view()
        self._refresh_compact_view()

    def _apply_calendar_formats(self) -> None:
        default_format = QTextCharFormat()
        default_format.setBackground(Qt.transparent)
        start = self.calendar.minimumDate()
        end = self.calendar.maximumDate()
        current = QDate(start)
        while current <= end:
            self.calendar.setDateTextFormat(current, default_format)
            current = current.addDays(1)

        for task_date, summary in self.markers.items():
            format_ = QTextCharFormat()
            background, foreground = self._colors_for_status(summary.dominant_status)
            format_.setBackground(background)
            format_.setForeground(foreground)
            format_.setToolTip(
                f"{summary.total} task(s), "
                f"in progress {summary.in_progress}, "
                f"scheduled {summary.scheduled}, "
                f"completed {summary.completed}"
            )
            format_.setFontUnderline(summary.in_progress > 0 or summary.on_hold > 0)
            self.calendar.setDateTextFormat(
                QDate(task_date.year, task_date.month, task_date.day),
                format_,
            )

    def _colors_for_status(self, status: TaskStatus | None) -> tuple[QColor, QColor]:
        if status == TaskStatus.IN_PROGRESS:
            return QColor("#f5b041"), QColor("#1f2933")
        if status == TaskStatus.ON_HOLD:
            return QColor("#d6dbdf"), QColor("#1f2933")
        if status == TaskStatus.COMPLETED:
            return QColor("#7dcea0"), QColor("#0b3d2e")
        if status == TaskStatus.CANCELLED:
            return QColor("#f1948a"), QColor("#641e16")
        return QColor("#85c1e9"), QColor("#0b2239")

    def _emit_calendar_date(self, qdate: QDate) -> None:
        self._refresh_week_view()
        self.dateActivated.emit(date(qdate.year(), qdate.month(), qdate.day()))

    def _emit_list_item_date(self, item: QListWidgetItem) -> None:
        item_date = item.data(Qt.ItemDataRole.UserRole)
        if item_date:
            self.set_selected_date(item_date)
            self.dateActivated.emit(item_date)

    def _refresh_week_view(self) -> None:
        self.week_list.clear()
        selected = self.selected_date()
        start = selected - timedelta(days=selected.weekday())
        for index in range(7):
            current = start + timedelta(days=index)
            summary = self.markers.get(current)
            total = summary.total if summary else 0
            status = summary.dominant_status.value if summary and summary.dominant_status else "none"
            item = QListWidgetItem(f"{current.isoformat()}  tasks:{total}  status:{status}")
            item.setData(Qt.ItemDataRole.UserRole, current)
            self.week_list.addItem(item)

    def _refresh_compact_view(self) -> None:
        self.compact_list.clear()
        today = date.today()
        for offset in range(14):
            current = today + timedelta(days=offset)
            summary = self.markers.get(current)
            total = summary.total if summary else 0
            status = summary.dominant_status.value if summary and summary.dominant_status else "none"
            item = QListWidgetItem(f"{current.isoformat()}  tasks:{total}  status:{status}")
            item.setData(Qt.ItemDataRole.UserRole, current)
            self.compact_list.addItem(item)
