from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
        self.background_color = "#334155"
        self.border_color = "#64748b"
        self.header_color = "#334155"

        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["month", "week", "compact"])
        self.mode_selector.currentTextChanged.connect(self._switch_mode)

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.clicked.connect(self._emit_calendar_date)

        self.week_grid = QFrame()
        self.week_grid.setObjectName("calendarCards")
        self.week_grid_layout = QGridLayout(self.week_grid)
        self.week_grid_layout.setContentsMargins(0, 0, 0, 0)
        self.week_grid_layout.setSpacing(10)
        self.week_cards: list[QPushButton] = []

        self.compact_grid = QFrame()
        self.compact_grid.setObjectName("calendarCards")
        self.compact_grid_layout = QGridLayout(self.compact_grid)
        self.compact_grid_layout.setContentsMargins(0, 0, 0, 0)
        self.compact_grid_layout.setSpacing(8)
        self.compact_cards: list[QPushButton] = []

        self.stack = QStackedWidget()
        self.stack.addWidget(self.calendar)
        self.stack.addWidget(self.week_grid)
        self.stack.addWidget(self.compact_grid)
        self._apply_colors()

        self.header_widget = QWidget()
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(QLabel("Calendar style"))
        header.addWidget(self.mode_selector)
        header.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.header_widget)
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
        self._refresh_compact_view()

    def marker_for(self, selected: date) -> CalendarDaySummary | None:
        return self.markers.get(selected)

    def set_background_color(self, color: str) -> None:
        selected = QColor(color)
        if not selected.isValid():
            return
        self.background_color = selected.name()
        self._apply_colors()

    def set_border_color(self, color: str) -> None:
        selected = QColor(color)
        if not selected.isValid():
            return
        self.border_color = selected.name()
        self._apply_colors()

    def set_header_color(self, color: str) -> None:
        selected = QColor(color)
        if not selected.isValid():
            return
        self.header_color = selected.name()
        self._apply_colors()

    def _apply_colors(self) -> None:
        panel_background = self._rgba_from_hex(self.background_color, 138)
        panel_hover = self._rgba_from_hex(self.background_color, 172)
        card_background = self._rgba_from_hex(self.background_color, 154)
        card_hover = self._rgba_from_hex(self.background_color, 190)
        task_card_background = self._rgba_from_hex(self.background_color, 214)
        border_color = self._rgba_from_hex(self.border_color, 210)
        header_background = self._rgba_from_hex(self.header_color, 224)
        header_control_background = self._rgba_from_hex(self.header_color, 242)
        header_control_hover = self._rgba_from_hex(self.header_color, 255)
        self.calendar.setStyleSheet(
            "QCalendarWidget QWidget { background: transparent; color: rgba(255,255,255,220); }"
            "QCalendarWidget QAbstractItemView {"
            f"background: {panel_background}; background-color: {panel_background}; color: rgba(255,255,255,225);"
            "selection-background-color: rgba(93, 173, 226, 0.55);"
            f"selection-color: white; border: 1px solid {border_color}; border-radius: 12px;"
            "}"
            f"QCalendarWidget QAbstractItemView::item {{ background-color: {panel_background}; }}"
            f"QCalendarWidget QAbstractItemView:hover {{ background: {panel_hover}; }}"
            f"QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {header_background}; border: 1px solid {border_color}; border-radius: 10px; }}"
            f"QCalendarWidget QToolButton {{ color: white; background: {header_control_background}; border-radius: 8px; padding: 5px; }}"
            f"QCalendarWidget QToolButton:hover {{ background: {header_control_hover}; }}"
            f"QCalendarWidget QMenu {{ background: {header_control_background}; color: white; }}"
            f"QCalendarWidget QSpinBox {{ background: {header_control_background}; color: white; border-radius: 6px; }}"
        )
        self._style_month_viewport(panel_background)
        if self.markers:
            self._apply_calendar_formats()
        self.week_grid.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.compact_grid.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.stack.setStyleSheet(
            f"#calendarCards {{ background: {panel_background}; border-radius: 14px; }}"
            "QPushButton[calendarCard='true'] {"
            f"background: {card_background}; color: rgba(255,255,255,225);"
            "border: 1px solid rgba(255,255,255,0.16); border-radius: 14px; padding: 10px; text-align: left;"
            "}"
            f"QPushButton[calendarCard='true']:hover {{ background: {card_hover}; border-color: rgba(255,255,255,0.28); }}"
            f"QPushButton[calendarCard='true'][hasTasks='true'] {{ background: {task_card_background}; border-color: rgba(133,193,233,0.55); }}"
            "QPushButton[calendarCard='true'][selected='true'] { border: 2px solid rgba(255,255,255,0.72); }"
        )

    def _style_month_viewport(self, background: str) -> None:
        month_view = self.calendar.findChild(QAbstractItemView)
        if month_view is None:
            return
        month_view.setProperty("calendarContentBackground", background)
        month_view.viewport().setProperty("calendarContentBackground", background)
        month_view.viewport().setStyleSheet(f"background-color: {background};")
        month_view.viewport().setAutoFillBackground(True)

    @staticmethod
    def _rgba_from_hex(color: str, alpha: int) -> str:
        selected = QColor(color)
        if not selected.isValid():
            selected = QColor("#334155")
        return f"rgba({selected.red()}, {selected.green()}, {selected.blue()}, {alpha})"

    def _switch_mode(self, mode: str) -> None:
        index = {"month": 0, "week": 1, "compact": 2}[mode]
        self.stack.setCurrentIndex(index)
        self._refresh_week_view()
        self._refresh_compact_view()

    def _apply_calendar_formats(self) -> None:
        default_format = QTextCharFormat()
        default_format.setBackground(QColor(self.background_color))
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

    def _emit_card_date(self, selected: date) -> None:
        self.set_selected_date(selected)
        self.dateActivated.emit(selected)

    def _refresh_week_view(self) -> None:
        self._clear_layout(self.week_grid_layout)
        self.week_cards.clear()
        selected = self.selected_date()
        start = selected - timedelta(days=selected.weekday())
        for index in range(7):
            current = start + timedelta(days=index)
            card = self._make_day_card(current, selected)
            self.week_grid_layout.addWidget(card, 0, index)
            self.week_cards.append(card)

    def _refresh_compact_view(self) -> None:
        self._clear_layout(self.compact_grid_layout)
        self.compact_cards.clear()
        today = date.today()
        for offset in range(14):
            current = today + timedelta(days=offset)
            row, column = divmod(offset, 7)
            card = self._make_day_card(current, self.selected_date(), compact=True)
            self.compact_grid_layout.addWidget(card, row, column)
            self.compact_cards.append(card)

    def _make_day_card(self, current: date, selected: date, compact: bool = False) -> QPushButton:
        summary = self.markers.get(current)
        total = summary.total if summary else 0
        status = summary.dominant_status.value if summary and summary.dominant_status else "none"
        priority = f"P{summary.highest_priority}" if summary and summary.highest_priority is not None else "No priority"
        pinned = "  ★" if summary and summary.has_pinned else ""
        date_label = f"{current:%a} {current.day}" if not compact else f"{current.month}/{current.day}"
        detail = self._summary_detail(summary)
        card = QPushButton(f"{date_label}{pinned}\n{total} task(s) · {status}\n{priority} · {detail}")
        card.setProperty("calendarCard", True)
        card.setProperty("hasTasks", total > 0)
        card.setProperty("selected", current == selected)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setMinimumHeight(104 if not compact else 82)
        card.clicked.connect(lambda _checked=False, target=current: self._emit_card_date(target))
        return card

    def _summary_detail(self, summary: CalendarDaySummary | None) -> str:
        if not summary:
            return "clear"
        active = summary.in_progress + summary.scheduled + summary.blocked + summary.on_hold
        return f"{active} active / {summary.completed} done"

    def _clear_layout(self, layout: QGridLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
