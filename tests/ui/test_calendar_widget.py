from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt

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
    assert widget.compact_list.count() == 14
