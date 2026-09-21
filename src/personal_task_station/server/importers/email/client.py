from __future__ import annotations

import email
import imaplib
import ssl
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


@dataclass
class ImapConfig:
    host: str
    port: int = 993
    username: str = ""
    password: str = ""
    use_ssl: bool = True
    folder: str = "INBOX"


@dataclass
class FetchedEmail:
    uid: str
    subject: str
    from_addr: str
    date: str
    body_html: str
    body_text: str
    attachments: list[tuple[str, bytes]]


class EmailClient:
    # QQ/163 style servers refuse SELECT until an IMAP ID command is issued.
    _ID_REQUIRED_SENDERS = ("qq.com", "163.com", "126.com")

    def __init__(self, config: ImapConfig):
        self.config = config
        self._conn: imaplib.IMAP4_SSL | imaplib.IMAP4 | None = None

    def connect(self) -> None:
        if self.config.use_ssl:
            ctx = ssl.create_default_context()
            self._conn = imaplib.IMAP4_SSL(self.config.host, self.config.port, ssl_context=ctx)
        else:
            self._conn = imaplib.IMAP4(self.config.host, self.config.port)
        self._conn.login(self.config.username, self.config.password)
        self._send_imap_id()

    def _send_imap_id(self) -> None:
        """Announce client identity for servers requiring RFC 2971 ID.

        QQ Mail (and Netease mailboxes) return ``Unsafe Login`` errors on any
        subsequent command unless an ID command is issued right after login;
        harmless elsewhere because failures are swallowed.
        """
        conn = self._conn
        if conn is None:
            return
        try:
            required = any(
                marker in str(self.config.host).lower()
                or marker in self.config.username.lower()
                for marker in self._ID_REQUIRED_SENDERS
            )
            if not required:
                return
            from imaplib import Commands

            Commands.setdefault("ID", ("AUTH",))
            conn._simple_command(  # noqa: SLF001 - imaplib exposes no public ID helper
                "ID",
                '("name" "personal-task-station" "version" "0.1.0")',
            )
        except Exception:  # noqa: BLE001 - identity hints are best-effort only
            pass

    def disconnect(self) -> None:
        if self._conn:
            try:
                self._conn.close()
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def __enter__(self) -> "EmailClient":
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.disconnect()

    def fetch_unseen_since(
        self,
        since_date: date | None = None,
        ignore_seen: bool = False,
        sender_filter: list[str] | None = None,
    ) -> list[FetchedEmail]:
        if not self._conn:
            raise RuntimeError("Not connected")
        since = since_date or (date.today() - timedelta(days=30))
        since_str = since.strftime("%d-%b-%Y")
        self._conn.select(self.config.folder)
        criteria = f'(SINCE "{since_str}")' if ignore_seen else f'(UNSEEN SINCE "{since_str}")'
        typ, data = self._conn.search(None, criteria)
        if typ != "OK" or not data[0]:
            return []
        uids = data[0].split()
        emails: list[FetchedEmail] = []
        for uid in uids:
            # Cheap header-only fetch first to filter by sender
            if sender_filter:
                typ2, hdr = self._conn.fetch(uid, "(BODY[HEADER.FIELDS (FROM)])")
                if typ2 != "OK" or not hdr:
                    continue
                raw_hdr = hdr[0][1] if isinstance(hdr[0], tuple) else b""
                from_val = str(email.message_from_bytes(raw_hdr).get("From", ""))
                if not any(s in from_val for s in sender_filter):
                    continue
            typ, msg_data = self._conn.fetch(uid, "(RFC822)")
            if typ != "OK" or not msg_data:
                continue
            raw_msg = msg_data[0][1] if isinstance(msg_data[0], tuple) else b""
            msg = email.message_from_bytes(raw_msg)
            parsed = self._parse_message(uid.decode(), msg)
            if parsed:
                emails.append(parsed)
        return emails

    def mark_seen(self, uid: str) -> None:
        if self._conn:
            self._conn.store(uid.encode(), "+FLAGS", "\\Seen")

    def _parse_message(self, uid: str, msg: email.message.Message) -> FetchedEmail | None:
        subject = self._decode_header(msg.get("Subject", ""))
        from_addr = self._decode_header(msg.get("From", ""))
        date_str = msg.get("Date", "")
        body_html = ""
        body_text = ""
        attachments: list[tuple[str, bytes]] = []
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                cdisp = str(part.get("Content-Disposition", ""))
                if "attachment" in cdisp:
                    filename = part.get_filename() or "unknown"
                    payload = part.get_payload(decode=True) or b""
                    attachments.append((filename, payload))
                elif ctype == "text/html":
                    body_html = self._decode_payload(part, part.get_payload(decode=True))
                elif ctype == "text/plain":
                    body_text = self._decode_payload(part, part.get_payload(decode=True))
        else:
            payload = msg.get_payload(decode=True) or b""
            text = self._decode_payload(msg, payload)
            if msg.get_content_type() == "text/html":
                body_html = text
            else:
                body_text = text
        return FetchedEmail(
            uid=uid,
            subject=subject,
            from_addr=from_addr,
            date=date_str,
            body_html=body_html,
            body_text=body_text,
            attachments=attachments,
        )

    @staticmethod
    def _decode_payload(part: email.message.Message, payload: bytes | None) -> str:
        """Decode a text part honoring its charset (Chinese banks love GBK)."""
        if not payload:
            return ""
        charset = part.get_content_charset() or "utf-8"
        for candidate in (charset, "utf-8", "gbk"):
            try:
                return payload.decode(candidate)
            except (UnicodeDecodeError, LookupError):
                continue
        return payload.decode("utf-8", errors="replace")

    def _decode_header(self, value: str) -> str:
        from email.header import decode_header
        parts = decode_header(value)
        result = []
        for part, charset in parts:
            if isinstance(part, bytes):
                try:
                    result.append(part.decode(charset or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    result.append(part.decode("utf-8", errors="replace"))
            else:
                result.append(part)
        return "".join(result)
