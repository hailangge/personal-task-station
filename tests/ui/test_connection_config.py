from __future__ import annotations

from pathlib import Path

from personal_task_station.client.config import ClientSettingsStore
from personal_task_station.client.views.connection_view import ConnectionConfigWidget
from personal_task_station.shared.schemas import ClientSettings


def test_connection_widget_save_and_load(qtbot, tmp_path: Path):
    widget = ConnectionConfigWidget()
    qtbot.addWidget(widget)
    widget.base_url_input.setText("https://tasks.example.test")
    widget.api_key_input.setText("secret")
    widget.server_cert_path_input.setText("/certs/ca-cert.pem")
    widget.allow_local_http_input.setChecked(True)

    settings = ClientSettings(connection=widget.get_config())
    store = ClientSettingsStore(tmp_path / "config.json")
    store.save(settings)
    loaded = store.load()
    assert loaded.connection.base_url == "https://tasks.example.test"
    assert loaded.connection.api_key == "secret"
    assert loaded.connection.server_cert_path == "/certs/ca-cert.pem"
    assert loaded.connection.allow_insecure_localhost is True


def test_client_settings_store_persists_desktop_display_preferences(tmp_path: Path):
    settings = ClientSettings.model_validate(
        {
            "desktop": {
                "opacity": 0.66,
                "calendar_mode": "week",
                "always_on_top": False,
                "window_x": 12,
                "window_y": 34,
                "main_background_color": "#14b8a6",
                "calendar_background_color": "#312e81",
                "calendar_border_color": "#f97316",
                "calendar_header_color": "#0f766e",
            }
        }
    )
    store = ClientSettingsStore(tmp_path / "config.json")

    store.save(settings)
    loaded = store.load()

    assert loaded.desktop.opacity == 0.66
    assert loaded.desktop.calendar_mode == "week"
    assert loaded.desktop.always_on_top is False
    assert loaded.desktop.window_x == 12
    assert loaded.desktop.window_y == 34
    assert loaded.desktop.main_background_color == "#14b8a6"
    assert loaded.desktop.calendar_background_color == "#312e81"
    assert loaded.desktop.calendar_border_color == "#f97316"
    assert loaded.desktop.calendar_header_color == "#0f766e"
