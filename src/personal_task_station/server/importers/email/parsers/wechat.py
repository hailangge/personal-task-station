from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from personal_task_station.server.importers.base import ImportResult, RawTransaction
from personal_task_station.server.importers.email.client import FetchedEmail
from personal_task_station.server.importers.email.parser_base import EmailParserBase
from personal_task_station.shared.enums import BillDirection


class WechatEmailParser(EmailParserBase):
    """Parser for WeChat Pay (微信支付) notification emails.

    Typical sender: wechat.com, pay@wechat.com, service@wechat.com
    """

    source_name = "wechat_email"
    sender_patterns = ["wechat.com", "pay@wechat", "service@wechat"]
    subject_patterns = ["微信支付", "交易提醒", "支付凭证", "WeChat Pay"]

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
            r"支付金额[：:]\s*[¥￥]?\s*([\d,]+\.\d{2})",
            r"金额[：:]\s*[¥￥]?\s*([\d,]+\.\d{2})",
            r"([\d,]+\.\d{2})\s*元",
            r"[¥￥]\s*([\d,]+\.\d{2})",
        ]:
            amount_match = re.search(pattern, text)
            if amount_match:
                break

        if not amount_match:
            return transactions

        amount = Decimal(amount_match.group(1).replace(",", ""))

        merchant = "微信支付"
        for pattern in [
            r"商户[：:]\s*(.+?)(?:\n|$)",
            r"商家[：:]\s*(.+?)(?:\n|$)",
            r"交易对象[：:]\s*(.+?)(?:\n|$)",
            r"商品[：:]\s*(.+?)(?:\n|$)",
        ]:
            m = re.search(pattern, text)
            if m:
                merchant = m.group(1).strip()[:50]
                break

        occurred_on = date.today()
        for pattern in [
            r"支付时间[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            r"交易时间[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}:\d{2})",
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

        direction = BillDirection.EXPENSE
        if any(kw in text for kw in ["退款", "入账", "收款", "零钱到账", "转入"]):
            direction = BillDirection.INCOME

        transactions.append(RawTransaction(
            source_name=self.source_name,
            occurred_on=occurred_on,
            amount=amount,
            direction=direction,
            merchant_name=merchant,
            channel="wechat_email",
            raw_data={},
        ))
        return transactions
