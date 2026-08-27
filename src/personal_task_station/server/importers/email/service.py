from __future__ import annotations

from datetime import date, timedelta

from personal_task_station.server.importers.base import ImportResult
from personal_task_station.server.importers.email.client import EmailClient, FetchedEmail, ImapConfig
from personal_task_station.server.importers.email.parser_base import EmailParserBase
from personal_task_station.server.importers.email.parsers import PARSERS
from personal_task_station.shared.settings import AppSettings


class EmailImportService:
    """Service that fetches emails and routes them to the appropriate parser.

    When ``bill_only`` is enabled (default), an email is processed only when it
    looks bill-related: either the subject contains one of the billing keywords
    below, or the sender is a known finance domain **and** the mail carries a
    zip/pdf attachment (official bills/invoices). Everything else is skipped so
    personal inboxes never leak unrelated content into the ledger.
    """

    PARSERS: list[type[EmailParserBase]] = PARSERS

    BILL_SUBJECT_KEYWORDS: tuple[str, ...] = (
        "账单",
        "对账单",
        "交易流水",
        "流水证明",
        "月度账单",
        "发票",
        "invoice",
        "支付成功",
        "交易提醒",
        "收款提醒",
        "动账通知",
    )

    KNOWN_FINANCE_SENDERS: tuple[str, ...] = (
        "alipay.com",
        "tenpay.com",
        "wechatpay",
        "cmbchina.com",
        "bankcomm.com",
        "icbc.com.cn",
        "ccb.com",
        "boc.cn",
        "abchina.com",
        "psbc.com",
        "jd.com",
        "paypal.com",
    )

    def __init__(
        self,
        config: ImapConfig,
        settings: AppSettings | None = None,
        bill_only: bool | None = None,
    ):
        self.config = config
        self.settings = settings or AppSettings.load()
        if bill_only is not None:
            self.bill_only = bill_only
        else:
            self.bill_only = getattr(self.settings, "email_bill_only", True)

    def import_from_email(
        self,
        since_date: date | None = None,
        mark_seen: bool = True,
        ignore_seen: bool = False,
    ) -> list[ImportResult]:
        """Fetch emails since *since_date* and parse transactions.

        Set ignore_seen=True to re-process already-read emails.
        Returns one ImportResult per email that matched a parser.
        """
        since = since_date or (date.today() - timedelta(days=30))
        results: list[ImportResult] = []

        # Only download emails from known sender domains when re-importing all mail
        sender_filter = self._all_sender_patterns() if ignore_seen else None

        with EmailClient(self.config) as client:
            emails = client.fetch_unseen_since(since, ignore_seen=ignore_seen, sender_filter=sender_filter)
            for email in emails:
                if self.bill_only and not self.is_bill_related(email):
                    continue
                parser = self._find_parser(email)
                if parser is None:
                    continue
                result = parser.parse(
                    email,
                    since_date=since,
                    passwords=getattr(self.settings, "bill_zip_passwords", ()),
                )
                if result.raw_transactions or result.errors:
                    results.append(result)
                if mark_seen:
                    client.mark_seen(email.uid)
        return results

    def preview_emails(
        self, since_date: date | None = None, ignore_seen: bool = False
    ) -> list[FetchedEmail]:
        """Fetch emails without marking them as read or parsing."""
        since = since_date or (date.today() - timedelta(days=30))
        with EmailClient(self.config) as client:
            return client.fetch_unseen_since(since, ignore_seen=ignore_seen)

    @classmethod
    def is_bill_related(cls, email: FetchedEmail) -> bool:
        """Coarse gate deciding whether an email may touch the ledger at all."""
        subject_hit = any(keyword in email.subject for keyword in cls.BILL_SUBJECT_KEYWORDS)
        if subject_hit:
            return True
        has_attachment = any(
            name.lower().endswith((".zip", ".pdf", ".csv")) for name, _ in email.attachments
        )
        sender_hit = any(domain in email.from_addr.lower() for domain in cls.KNOWN_FINANCE_SENDERS)
        return bool(has_attachment and sender_hit)

    def _find_parser(self, email: FetchedEmail) -> EmailParserBase | None:
        for parser_cls in self.PARSERS:
            parser = parser_cls()
            if parser.can_parse(email):
                return parser
        return None

    def _all_sender_patterns(self) -> list[str]:
        patterns: list[str] = []
        for cls in self.PARSERS:
            patterns.extend(cls.sender_patterns)
        return patterns

