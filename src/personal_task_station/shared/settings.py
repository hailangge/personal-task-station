from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bill_zip_passwords() -> tuple[str, ...]:
    """Collect candidate passwords for encrypted bill zip attachments.

    Named variables come first so operators can pin provider-specific secrets;
    ``PTS_BILL_ZIP_PASSWORDS`` accepts a comma-separated list for extra keys.
    """
    passwords: list[str] = []
    for env_name in ("PTS_WECHAT_BILL_ZIP_PASSWORD", "PTS_ALIPAY_BILL_ZIP_PASSWORD"):
        value = os.environ.get(env_name, "").strip()
        if value and value not in passwords:
            passwords.append(value)
    raw = os.environ.get("PTS_BILL_ZIP_PASSWORDS", "")
    for part in raw.split(","):
        value = part.strip()
        if value and value not in passwords:
            passwords.append(value)
    return tuple(passwords)


@dataclass(slots=True)
class AppSettings:
    database_url: str
    api_key: str
    host: str
    port: int
    ssl_certfile: str | None
    ssl_keyfile: str | None
    ssl_cafile: str | None
    server_cert_path: str | None
    client_cert_path: str | None
    client_key_path: str | None
    litellm_base_url: str | None
    litellm_model: str | None
    litellm_api_key: str | None
    request_timeout_seconds: float
    # Automated ingestion settings (email monitoring / poller / webhook).
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_folder: str = "INBOX"
    imap_use_ssl: bool = True
    email_poll_seconds: int = 0
    email_bill_only: bool = True
    bill_zip_passwords: tuple[str, ...] = ()

    @classmethod
    def load(cls) -> "AppSettings":
        repo_root = Path(os.environ.get("PTS_REPO_ROOT", Path.cwd()))
        default_db = repo_root / ".local" / "personal_task_station.sqlite3"
        return cls(
            database_url=os.environ.get("PTS_DATABASE_URL", f"sqlite:///{default_db}"),
            api_key=os.environ.get("PTS_API_KEY", "dev-token"),
            host=os.environ.get("PTS_HOST", "127.0.0.1"),
            port=int(os.environ.get("PTS_PORT", "8000")),
            ssl_certfile=os.environ.get("PTS_SSL_CERTFILE"),
            ssl_keyfile=os.environ.get("PTS_SSL_KEYFILE"),
            ssl_cafile=os.environ.get("PTS_SSL_CAFILE"),
            server_cert_path=os.environ.get("PTS_SERVER_CERT_PATH"),
            client_cert_path=os.environ.get("PTS_CLIENT_CERT_PATH"),
            client_key_path=os.environ.get("PTS_CLIENT_KEY_PATH"),
            litellm_base_url=os.environ.get("PTS_LITELLM_BASE_URL"),
            litellm_model=os.environ.get("PTS_LITELLM_MODEL"),
            litellm_api_key=os.environ.get("PTS_LITELLM_API_KEY"),
            request_timeout_seconds=float(os.environ.get("PTS_REQUEST_TIMEOUT_SECONDS", "15")),
            imap_host=os.environ.get("PTS_IMAP_HOST", ""),
            imap_port=int(os.environ.get("PTS_IMAP_PORT", "993")),
            imap_username=os.environ.get("PTS_IMAP_USERNAME", ""),
            imap_password=os.environ.get("PTS_IMAP_PASSWORD", ""),
            imap_folder=os.environ.get("PTS_IMAP_FOLDER", "INBOX"),
            imap_use_ssl=os.environ.get("PTS_IMAP_USE_SSL", "1") == "1",
            email_poll_seconds=int(os.environ.get("PTS_EMAIL_POLL_SECONDS", "0")),
            email_bill_only=os.environ.get("PTS_EMAIL_BILL_ONLY", "1") == "1",
            bill_zip_passwords=_bill_zip_passwords(),
        )
