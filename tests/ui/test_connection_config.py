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
