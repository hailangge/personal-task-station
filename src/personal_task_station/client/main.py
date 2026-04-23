from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from personal_task_station.client.api_client import ServerApiClient
from personal_task_station.client.config import ClientSettingsStore
from personal_task_station.client.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    store = ClientSettingsStore()
    settings = store.load()
    client = ServerApiClient(settings.connection)
    window = MainWindow(client, store, settings)
    window.show()
    try:
        window.refresh_all()
    except Exception as exc:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(window, "Connection", f"Failed to sync with server: {exc}")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
