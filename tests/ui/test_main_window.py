from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent
from PySide6.QtWidgets import QSizeGrip, QSystemTrayIcon, QToolButton

from personal_task_station.client.main_window import MainWindow
from personal_task_station.shared.enums import BillDirection
from personal_task_station.shared.schemas import ClientSettings, ImportJobRead, MergedTransactionRead, MonthlySummary


class DummyApiClient:
    def __init__(self):
        self.imports: list[tuple[str, str]] = []
        self.undone_duplicates: list[int] = []
        self.reanalyze_count = 0

    def list_tasks(self, **kwargs):
        return []

    def calendar_summary(self, start, end):
        return []

    def monthly_summary(self, year, month):
        return MonthlySummary(
            month=f"{year}-{month:02d}",
            total_expense=Decimal("25.50"),
            total_income=Decimal("0.00"),
            by_category={"groceries": Decimal("25.50")},
            by_source={"fixture": Decimal("25.50")},
            by_account={"card:1234": Decimal("25.50")},
            duplicates=[
                MergedTransactionRead(
                    id=7,
                    occurred_on=date(2026, 3, 1),
                    amount=Decimal("25.50"),
                    direction=BillDirection.EXPENSE,
                    merchant_name="Fresh Market",
                    normalized_merchant="freshmarket",
                    source_name="fixture",
                    category="groceries",
                    confidence=0.9,
                    reason="Grouped duplicate transactions.",
                    duplicate_count=1,
                    is_active=True,
                    created_at=datetime(2026, 3, 1, 12, 0, 0),
                )
            ],
            anomalies=[],
        )

    def list_transactions(self, month):
        return []

    def import_billing_file(self, source_name, file_path):
        self.imports.append((source_name, file_path))
        return ImportJobRead(
            id=3,
            source_name=source_name,
            filename="sample_transactions.csv",
            status="completed",
            raw_count=5,
            normalized_count=5,
            merged_count=4,
            error_message="",
            logs=[],
            created_at=datetime(2026, 3, 1, 12, 0, 0),
        )

    def undo_merge(self, merged_transaction_id):
        self.undone_duplicates.append(merged_transaction_id)
        return {"status": "ok"}

    def reanalyze(self, import_job_id=None):
        self.reanalyze_count += 1
        return {"status": "ok"}

    def health(self):
        return {"status": "ok"}


class MemorySettingsStore:
    def __init__(self):
        self.saved: list[ClientSettings] = []

    def save(self, settings: ClientSettings) -> None:
        self.saved.append(settings)


def _make_window(qtbot, settings: ClientSettings | None = None, api_client: DummyApiClient | None = None):
    store = MemorySettingsStore()
    window = MainWindow(api_client or DummyApiClient(), store, settings or ClientSettings())
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window, store


def test_main_window_defaults_to_compact_floating_widget(qtbot):
    window, _store = _make_window(qtbot)

    assert window.width() == 920
    assert window.height() == 620
    assert window.windowOpacity() == pytest.approx(0.82, abs=0.01)
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert window.windowFlags() & Qt.WindowType.Tool
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert window.pos() == window._default_top_right_position()
    assert window.minimumWidth() == 520
    assert window.findChild(QSizeGrip) is not None


def test_main_window_restores_saved_position(qtbot):
    settings = ClientSettings.model_validate({
        "desktop": {"window_x": 111, "window_y": 222}
    })
    window, _store = _make_window(qtbot, settings)

    assert window.pos() == QPoint(111, 222)


def test_main_window_drag_persists_position(qtbot):
    window, store = _make_window(qtbot)
    start = window.pos()
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(20, 20),
        QPointF(window.mapToGlobal(QPoint(20, 20))),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(60, 60),
        QPointF(window.mapToGlobal(QPoint(160, 110))),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(60, 60),
        QPointF(window.mapToGlobal(QPoint(160, 110))),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )

    window.mousePressEvent(press)
    window.mouseMoveEvent(move)
    window.mouseReleaseEvent(release)

    assert window.pos() != start
    assert store.saved
    assert store.saved[-1].desktop.window_x == window.x()
    assert store.saved[-1].desktop.window_y == window.y()


def test_always_on_top_toggle_preserves_position(qtbot):
    window, _store = _make_window(qtbot)
    window.move(123, 234)

    window.always_on_top_checkbox.setChecked(False)

    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert window.pos() == QPoint(123, 234)


def test_secondary_controls_are_collapsed_into_top_right_menu(qtbot):
    window, store = _make_window(qtbot)

    assert isinstance(window.refresh_button, QToolButton)
    assert window.refresh_button.text() == "↻"
    assert window.utility_button.menu() is window.utility_menu
    assert window.calendar_widget.header_widget.isHidden()
    assert window.opacity_slider.parentWidget() is not window
    assert window.always_on_top_action.isChecked() is True
    assert window.background_color_action.parent() is not window
    assert window.calendar_background_color_action.parent() is not window
    assert window.calendar_border_color_action.parent() is not window
    assert window.calendar_header_color_action.parent() is not window

    window.calendar_widget.mode_selector.setCurrentText("week")

    assert window.settings.desktop.calendar_mode == "week"
    assert store.saved[-1].desktop.calendar_mode == "week"


def test_main_window_applies_configured_background_color(qtbot):
    settings = ClientSettings.model_validate(
        {
            "desktop": {
                "main_background_color": "#7c3aed",
                "calendar_background_color": "#312e81",
                "calendar_border_color": "#f97316",
                "calendar_header_color": "#0f766e",
            }
        }
    )

    window, _store = _make_window(qtbot, settings)

    assert "background-color: rgba(124, 58, 237, 188)" in window.container.styleSheet()
    assert "background: rgba(49, 46, 129, 138)" in window.calendar_widget.calendar.styleSheet()
    assert "border: 1px solid rgba(249, 115, 22, 210)" in window.calendar_widget.calendar.styleSheet()
    assert "QCalendarWidget QWidget#qt_calendar_navigationbar { background: rgba(15, 118, 110, 224)" in window.calendar_widget.calendar.styleSheet()


def test_main_window_background_color_persists_and_restores(qtbot):
    window, store = _make_window(qtbot)

    window._set_main_background_color("#f97316")

    assert store.saved[-1].desktop.main_background_color == "#f97316"
    assert "background-color: rgba(249, 115, 22, 188)" in window.container.styleSheet()

    restored_window, _restored_store = _make_window(qtbot, store.saved[-1])

    assert "background-color: rgba(249, 115, 22, 188)" in restored_window.container.styleSheet()


def test_main_window_calendar_background_color_persists_and_restores(qtbot):
    window, store = _make_window(qtbot)

    window._set_calendar_background_color("#0f766e")

    assert store.saved[-1].desktop.calendar_background_color == "#0f766e"
    assert store.saved[-1].desktop.main_background_color == "#334155"
    assert "background: rgba(15, 118, 110, 138)" in window.calendar_widget.calendar.styleSheet()

    restored_window, _restored_store = _make_window(qtbot, store.saved[-1])

    assert "background: rgba(15, 118, 110, 138)" in restored_window.calendar_widget.calendar.styleSheet()
    assert "background-color: rgba(51, 65, 85, 188)" in restored_window.container.styleSheet()


def test_main_window_calendar_border_and_header_colors_persist_and_restore(qtbot):
    window, store = _make_window(qtbot)

    window._set_calendar_border_color("#f97316")
    window._set_calendar_header_color("#0f766e")

    assert store.saved[-1].desktop.calendar_border_color == "#f97316"
    assert store.saved[-1].desktop.calendar_header_color == "#0f766e"
    assert store.saved[-1].desktop.calendar_background_color == "#334155"
    assert "border: 1px solid rgba(249, 115, 22, 210)" in window.calendar_widget.calendar.styleSheet()
    assert "QCalendarWidget QWidget#qt_calendar_navigationbar { background: rgba(15, 118, 110, 224)" in window.calendar_widget.calendar.styleSheet()

    restored_window, _restored_store = _make_window(qtbot, store.saved[-1])

    assert "border: 1px solid rgba(249, 115, 22, 210)" in restored_window.calendar_widget.calendar.styleSheet()
    assert "QCalendarWidget QWidget#qt_calendar_navigationbar { background: rgba(15, 118, 110, 224)" in restored_window.calendar_widget.calendar.styleSheet()


def test_snap_to_screen_edges_persists_docked_position(qtbot):
    window, store = _make_window(qtbot)
    available = window.screen().availableGeometry()
    near_left = available.left() + window.WINDOW_MARGIN + 5
    near_top = available.top() + window.WINDOW_MARGIN + 4
    window.move(near_left, near_top)

    window._snap_to_screen_edges()
    window._persist_window_position()

    assert window.x() == available.left() + window.WINDOW_MARGIN
    assert window.y() == available.top() + window.WINDOW_MARGIN
    assert store.saved[-1].desktop.window_x == window.x()
    assert store.saved[-1].desktop.window_y == window.y()


def test_tray_menu_and_close_hide_window(qtbot):
    window, _store = _make_window(qtbot)

    assert isinstance(window.tray_icon, QSystemTrayIcon)
    assert window.tray_icon.contextMenu() is not None
    assert {action.text() for action in window.tray_icon.contextMenu().actions() if action.text()} >= {"Show", "Hide", "Quit"}

    close_event = QCloseEvent()
    window.closeEvent(close_event)

    assert not window.isVisible()
    assert not close_event.isAccepted()


def test_finance_refresh_populates_duplicate_table(qtbot):
    window, _store = _make_window(qtbot)

    window.refresh_finance()

    assert window.finance_view.expense_label.text() == "25.50"
    assert window.finance_view.category_table.item(0, 0).text() == "groceries"
    assert window.finance_view.duplicates_table.item(0, 0).text() == "7"
    assert window.finance_view.duplicates_table.item(0, 5).text() == "1"


def test_finance_undo_selected_duplicate_calls_api(qtbot):
    api_client = DummyApiClient()
    window, _store = _make_window(qtbot, api_client=api_client)
    window.refresh_finance()
    window.finance_view.duplicates_table.selectRow(0)

    window.undo_selected_duplicate()

    assert api_client.undone_duplicates == [7]
    assert "Undid duplicate merge 7" in window.finance_view.status_label.text()


def test_finance_reanalyze_calls_api(qtbot):
    api_client = DummyApiClient()
    window, _store = _make_window(qtbot, api_client=api_client)

    window.reanalyze_finance()

    assert api_client.reanalyze_count == 1
    assert "Reanalyzed" in window.finance_view.status_label.text()
