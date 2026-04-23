from __future__ import annotations

from datetime import date, timedelta

from personal_task_station.server.importers.base import ImportResult
from personal_task_station.server.importers.email.client import EmailClient, FetchedEmail, ImapConfig
from personal_task_station.server.importers.email.parser_base import EmailParserBase
from personal_task_station.server.importers.email.parsers import (
    AlipayEmailParser,
    CmbEmailParser,
    GenericNotificationParser,
    JdEmailParser,
    PddEmailParser,
    TaobaoEmailParser,
    WechatEmailParser,
)


class EmailImportService:
    """Service that fetches emails and routes them to the appropriate parser."""

    PARSERS: list[type[EmailParserBase]] = [
        CmbEmailParser,
        AlipayEmailParser,
        WechatEmailParser,
        JdEmailParser,
        TaobaoEmailParser,
        PddEmailParser,
        GenericNotificationParser,
    ]

    def __init__(self, config: ImapConfig):
        self.config = config

    def import_from_email(
        self,
        since_date: date | None = None,
        mark_seen: bool = True,
    ) -> list[ImportResult]:
        """Fetch unseen emails since *since_date* and parse transactions.

        Returns one ImportResult per email that matched a parser.
        """
        since = since_date or (date.today() - timedelta(days=30))
        results: list[ImportResult] = []

        with EmailClient(self.config) as client:
            emails = client.fetch_unseen_since(since)
            for email in emails:
                parser = self._find_parser(email)
                if parser is None:
                    continue
                result = parser.parse(email, since_date=since)
                if result.raw_transactions:
                    results.append(result)
                if mark_seen:
                    client.mark_seen(email.uid)
        return results

    def preview_emails(self, since_date: date | None = None) -> list[FetchedEmail]:
        """Fetch unseen emails without marking them as read or parsing."""
        since = since_date or (date.today() - timedelta(days=30))
        with EmailClient(self.config) as client:
            return client.fetch_unseen_since(since)

    def _find_parser(self, email: FetchedEmail) -> EmailParserBase | None:
        for parser_cls in self.PARSERS:
            parser = parser_cls()
            if parser.can_parse(email):
                return parser
        return None
