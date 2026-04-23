from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from personal_task_station.server.importers.base import ImportResult, RawTransaction
from personal_task_station.server.importers.email.client import FetchedEmail
from personal_task_station.server.importers.email.parser_base import EmailParserBase
from personal_task_station.shared.enums import BillDirection


class PddEmailParser(EmailParserBase):
    """Parser for Pinduoduo (拼多多) order confirmation emails.

    Typical sender: pinduoduo.com, service@pinduoduo.com
    """

    source_name = "pdd_email"
    sender_patterns = ["pinduoduo.com", "service@pinduoduo"]
    subject_patterns = ["订单", "支付成功", "拼多多", "pinduoduo"]

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

        amount_match = None
        for pattern in [
            r"实付金额[：:]\s*[¥￥]?\s*([\d,]+\.\d{2})",
            r"应付金额[：:]\s*[¥￥]?\s*([\d,]+\.\d{2})",
            r"订单金额[：:]\s*[¥￥]?\s*([\d,]+\.\d{2})",
        ]:
            amount_match = re.search(pattern, text)
            if amount_match:
                break

        if not amount_match:
            return transactions

        amount = Decimal(amount_match.group(1).replace(",", ""))

        merchant = "拼多多"
        for pattern in [
            r"店铺[：:]\s*(.+?)(?:\n|$)",
            r"商品[：:]\s*(.+?)(?:\n|$)",
        ]:
            m = re.search(pattern, text)
            if m:
                merchant = "拼多多 - " + m.group(1).strip()[:50]
                break

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
            channel="pdd_email",
            raw_data={},
        ))
        return transactions
