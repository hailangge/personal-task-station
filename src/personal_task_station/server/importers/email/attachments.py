"""Helpers for extracting bill data from email attachments.

Official WeChat Pay / Alipay monthly bills arrive as encrypted zip archives
containing a CSV member (the password is delivered out-of-band via SMS or the
email body itself). This module centralizes:

* opening encrypted zips with stdlib ``zipfile`` (PKWARE legacy crypto) and
  falling back to ``pyzipper`` for AES-encrypted archives when installed;
* decoding CSV members across encodings (utf-8-sig / gbk / latin-1).
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence


def decode_csv_bytes(data: bytes) -> str:
    """Decode raw CSV bytes trying common Chinese-bill encodings in order."""
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _read_member_with_pyzipper(data: bytes, member: str, password: str | None):
    try:
        import pyzipper  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            f"Zip member '{member}' requires AES support; install pyzipper "
            "(pip install 'personal-task-station[email]')"
        ) from exc
    with pyzipper.AESZipFile(io.BytesIO(data)) as zf:
        zf.setpassword(password.encode() if password else None)
        return zf.read(member)


def extract_csv_members(
    archive_bytes: bytes,
    passwords: Sequence[str] = (),
    *,
    suffixes: tuple[str, ...] = (".csv",),
) -> tuple[list[tuple[str, str]], list[str]]:
    """Return ``(members, errors)`` for CSV files inside a zip archive.

    Each member is ``(filename, decoded_text)``. Passwords are tried in order
    until one succeeds; unencrypted members are read without a password.
    """
    members: list[tuple[str, str]] = []
    errors: list[str] = []

    try:
        zf = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        return [], [f"invalid zip archive: {exc}"]

    with zf:
        names = [info.filename for info in zf.infolist()]
        wanted = [n for n in names if n.lower().endswith(suffixes)]
        if not wanted:
            return [], [f"no {suffixes} member found in zip (contents: {names[:10]})"]

        for name in wanted:
            info = zf.getinfo(name)
            encrypted = bool(info.flag_bits & 0x1)
            candidates = [""] if not encrypted else ["", *[p for p in passwords]]
            last_error: Exception | None = None
            content: bytes | None = None

            # Plain members and PKWARE legacy passwords go through stdlib;
            # NotImplementedError means AES/unsupported -> pyzipper fallback.
            for pwd in candidates:
                try:
                    content = zf.read(name, pwd=pwd.encode() if pwd else None)
                    break
                except NotImplementedError as exc:
                    last_error = exc
                    for fallback_pwd in candidates:
                        try:
                            content = _read_member_with_pyzipper(archive_bytes, name, fallback_pwd or None)
                            break
                        except Exception as nested_exc:  # noqa: BLE001
                            last_error = nested_exc
                    break
                except (RuntimeError, zipfile.BadZipFile) as exc:
                    last_error = exc
                    continue

            if content is None:
                message = f"{name}: wrong or missing password ({last_error})"
                errors.append(message)
                continue
            members.append((name, decode_csv_bytes(content)))

    return members, errors
