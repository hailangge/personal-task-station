from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from personal_task_station.server.importers.base import ImportResult, RawTransaction
from personal_task_station.server.importers.email.client import FetchedEmail
from personal_task_station.server.importers.email.parser_base import EmailParserBase
from personal_task_station.shared.enums import BillDirection


class JdEmailParser(EmailParserBase):
    """Parser for JD.com (京东) order confirmation emails.

    Typical sender: jd.com, service@jd.com
    """

    source_name = "jd_email"
    sender_patterns = ["jd.com", "service@jd"]
    subject_patterns = ["订单确认", "支付成功", "京东", "jd.com"]

    def parse(self, email: FetchedEmail, since_date: date | None = None) -> ImportResult:
        result = ImportResult(source_name=self.source_name)
        text = self._extract_text(email)
        if not text:
            result.errors.append("Empty email body")
            return result

        transactions = self._parse_transactions(text, since_date)
        result.raw_transactions.extend(transactions)
        return result

    def _parse_transactions(self, text: str, since_date: date | None) -> list[RawTransaction]:
        transactions: list[RawTransaction] = []

        # Amount patterns
        amount_match = None
        for pattern in [
            r"实付金额[：:]\s*[¥￥]?\s*([\d,]+\.\d{2})",
            r"订单金额[：:]\s*[¥￥]?\s*([\d,]+\.\d{2})",
            r"应付总额[：:]\s*[¥￥]?\s*([\d,]+\.\d{2})",
            r"合计[：:]\s*[¥￥]?\s*([\d,]+\.\d{2})",
        ]:
            amount_match = re.search(pattern, text)
            if amount_match:
                break

        if not amount_match:
            return transactions

        amount = Decimal(amount_match.group(1).replace(",", ""))

        # Merchant / product name
        merchant = "京东"
        for pattern in [
            r"商品名称[：:]\s*(.+?)(?:\n|$)",
            r"商品[：:]\s*(.+?)(?:\n|$)",
        ]:
            m = re.search(pattern, text)
            if m:
                merchant = "京东 - " + m.group(1).strip()[:50]
                break

        # Date
        occurred_on = date.today()
        for pattern in [
            r"下单时间[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2})",
        ]:
            m = re.search(pattern, text)
            if m:
                date_str = m.group(1).split()[0]
                try:
                    parts = re.split(r"[-/]", date_str)
                    occurred_on = date(int(parts[0]), int(parts[1]), int(parts[2]))
                except (ValueError, IndexError):
                    pass
                break

        if since_date and occurred_on < since_date:
            return transactions

        transactions.append(RawTransaction(
            source_name=self.source_name,
            occurred_on=occurred_on,
            amount=amount,
            direction=BillDirection.EXPENSE,
            merchant_name=merchant,
            channel="jd_email",
            raw_data={},
        ))
        return transactions
