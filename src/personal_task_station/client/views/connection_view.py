from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from personal_task_station.shared.schemas import ConnectionConfig


class ConnectionConfigWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.base_url_input = QLineEdit()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.server_cert_path_input = QLineEdit()
        self.client_cert_path_input = QLineEdit()
        self.client_key_path_input = QLineEdit()
        self.allow_local_http_input = QCheckBox("Allow local HTTP for development")
        self.https_note = QLabel("HTTPS is required. Provide server cert for self-signed.")
        self.https_note.setStyleSheet("color: gray;")
        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(1, 120)
        self.timeout_input.setValue(15)
        self.status_label = QLabel("")
        self.save_button = QPushButton("Save")
        self.test_button = QPushButton("Test connection")

        form = QFormLayout()
        form.addRow("Server URL", self.base_url_input)
        form.addRow("API key", self.api_key_input)
        form.addRow("Server cert path", self.server_cert_path_input)
        form.addRow("Client cert path", self.client_cert_path_input)
        form.addRow("Client key path", self.client_key_path_input)
        form.addRow("Local HTTP", self.allow_local_http_input)
        form.addRow("", self.https_note)
        form.addRow("Timeout (s)", self.timeout_input)

        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.test_button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)

    def set_config(self, config: ConnectionConfig) -> None:
        self.base_url_input.setText(config.base_url)
        self.api_key_input.setText(config.api_key)
        self.server_cert_path_input.setText(config.server_cert_path or "")
        self.client_cert_path_input.setText(config.client_cert_path or "")
        self.client_key_path_input.setText(config.client_key_path or "")
        self.allow_local_http_input.setChecked(config.allow_insecure_localhost)
        self.timeout_input.setValue(int(config.timeout_seconds))

    def get_config(self) -> ConnectionConfig:
        return ConnectionConfig(
            base_url=self.base_url_input.text().strip(),
            api_key=self.api_key_input.text().strip(),
            server_cert_path=self._optional_path(self.server_cert_path_input.text()),
            client_cert_path=self._optional_path(self.client_cert_path_input.text()),
            client_key_path=self._optional_path(self.client_key_path_input.text()),
            allow_insecure_localhost=self.allow_local_http_input.isChecked(),
            timeout_seconds=float(self.timeout_input.value()),
            verify_tls=True,
        )

    def _optional_path(self, raw: str) -> str | None:
        text = raw.strip()
        return text or None
