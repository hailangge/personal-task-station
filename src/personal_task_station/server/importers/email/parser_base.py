from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from personal_task_station.server.importers.base import ImportResult, RawTransaction
from personal_task_station.server.importers.email.client import FetchedEmail


class EmailParserBase(ABC):
    """Base class for email-based transaction parsers.

    Each parser handles a specific sender / email format.
    """

    source_name: str = ""
    sender_patterns: list[str] = []
    subject_patterns: list[str] = []

    def can_parse(self, email: FetchedEmail) -> bool:
        """Return True if this parser can handle the given email."""
        from_match = any(pattern in email.from_addr for pattern in self.sender_patterns)
        subj_match = any(pattern in email.subject for pattern in self.subject_patterns)
        return from_match or subj_match

    @abstractmethod
    def parse(self, email: FetchedEmail, since_date: date | None = None) -> ImportResult:
        ...

    def _extract_text(self, email: FetchedEmail) -> str:
        """Prefer HTML body, fallback to plain text."""
        return email.body_html or email.body_text or ""
