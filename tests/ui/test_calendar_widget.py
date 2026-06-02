from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QPushButton

from personal_task_station.client.widgets.calendar_widget import TaskCalendarWidget
from personal_task_station.shared.enums import TaskStatus
from personal_task_station.shared.schemas import CalendarDaySummary


def test_calendar_widget_switches_modes_and_marks_days(qtbot):
    widget = TaskCalendarWidget()
    qtbot.addWidget(widget)
    widget.set_markers(
        [
            CalendarDaySummary(
                date=date(2026, 4, 23),
                total=2,
                scheduled=1,
                in_progress=1,
                on_hold=0,
                completed=0,
                cancelled=0,
                dominant_status=TaskStatus.IN_PROGRESS,
            )
        ]
    )
    widget.mode_selector.setCurrentText("compact")
    assert widget.stack.currentIndex() == 2
    assert len(widget.compact_cards) == 14
    assert all(isinstance(card, QPushButton) for card in widget.compact_cards)
    assert all(card.property("calendarCard") for card in widget.compact_cards)


def test_calendar_week_mode_uses_clickable_visual_cards(qtbot):
    widget = TaskCalendarWidget()
    qtbot.addWidget(widget)
    widget.set_selected_date(date(2026, 4, 23))
    widget.set_markers(
        [
            CalendarDaySummary(
                date=date(2026, 4, 23),
                total=3,
                scheduled=1,
                in_progress=1,
                on_hold=0,
                blocked=1,
                completed=1,
                cancelled=0,
                has_pinned=True,
                highest_priority=1,
                dominant_status=TaskStatus.BLOCKED,
            )
        ]
    )

    widget.mode_selector.setCurrentText("week")

    assert widget.stack.currentIndex() == 1
    assert len(widget.week_cards) == 7
    marked_card = next(card for card in widget.week_cards if "3 task(s)" in card.text())
    assert marked_card.property("hasTasks") is True
    assert "★" in marked_card.text()
    assert "P1" in marked_card.text()


def test_calendar_widget_applies_configurable_panel_background(qtbot):
    widget = TaskCalendarWidget()
    qtbot.addWidget(widget)

    widget.set_background_color("#312e81")
    month_view = widget.calendar.findChild(QAbstractItemView)

    assert month_view is not None

    assert widget.background_color == "#312e81"
    assert month_view.property("calendarContentBackground") == "rgba(49, 46, 129, 138)"
    assert month_view.viewport().property("calendarContentBackground") == "rgba(49, 46, 129, 138)"
    assert month_view.viewport().styleSheet() == "background-color: rgba(49, 46, 129, 138);"
    assert "QCalendarWidget QAbstractItemView::item { background-color: rgba(49, 46, 129, 138); }" in widget.calendar.styleSheet()
    assert "background: rgba(49, 46, 129, 154)" in widget.stack.styleSheet()


def test_calendar_widget_applies_configurable_border_and_header_colors(qtbot):
    widget = TaskCalendarWidget()
    qtbot.addWidget(widget)

    widget.set_border_color("#f97316")
    widget.set_header_color("#0f766e")

    style = widget.calendar.styleSheet()
    assert widget.border_color == "#f97316"
    assert widget.header_color == "#0f766e"
    assert "border: 1px solid rgba(249, 115, 22, 210)" in style
    assert "QCalendarWidget QWidget#qt_calendar_navigationbar { background: rgba(15, 118, 110, 224)" in style
    assert "QCalendarWidget QToolButton { color: white; background: rgba(15, 118, 110, 242)" in style


def test_calendar_widget_applies_configurable_background_to_card_panels(qtbot):
    widget = TaskCalendarWidget()
    qtbot.addWidget(widget)

    widget.set_background_color("#0f766e")

    assert widget.week_grid.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    assert widget.compact_grid.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    assert "#calendarCards { background: rgba(15, 118, 110, 138)" in widget.stack.styleSheet()
    assert "QPushButton[calendarCard='true'] {background: rgba(15, 118, 110, 154)" in widget.stack.styleSheet()
