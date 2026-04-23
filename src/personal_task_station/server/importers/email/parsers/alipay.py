from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from personal_task_station.server.importers.base import ImportResult, RawTransaction
from personal_task_station.server.importers.email.client import FetchedEmail
from personal_task_station.server.importers.email.parser_base import EmailParserBase
from personal_task_station.shared.enums import BillDirection


class AlipayEmailParser(EmailParserBase):
    """Parser for Alipay (支付宝) notification emails.

    Handles payment confirmation emails and monthly statement emails.
    Typical sender: service@mail.alipay.com
    """

    source_name = "alipay_email"
    sender_patterns = ["alipay.com", "mail.alipay.com", "service@mail.alipay"]
    subject_patterns = ["支付成功", "交易提醒", "账单", "alipay", "支付宝"]

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

        # Pattern for payment notification:
        # "付款金额：123.45元" or "金额：¥123.45" or "交易金额 123.45"
        amount_patterns = [
            r"付款金额[：:]\s*[¥￥]?\s*([\d,]+\.\d{2})",
            r"交易金额[：:]\s*[¥￥]?\s*([\d,]+\.\d{2})",
            r"金额[：:]\s*[¥￥]?\s*([\d,]+\.\d{2})",
            r"[¥￥]\s*([\d,]+\.\d{2})",
        ]

        # Pattern for merchant:
        # "商户名称：某某商家" or "对方账户：xxx" or "商品名称：xxx"
        merchant_patterns = [
            r"商户名称[：:]\s*(.+?)(?:\n|$)",
            r"对方账户[：:]\s*(.+?)(?:\n|$)",
            r"商品名称[：:]\s*(.+?)(?:\n|$)",
            r"交易对方[：:]\s*(.+?)(?:\n|$)",
            r"商家[：:]\s*(.+?)(?:\n|$)",
        ]

        # Pattern for date:
        # "创建时间：2026-04-23 10:30:00" or "交易时间：2026/04/23"
        date_patterns = [
            r"(?:创建|交易|付款)时间[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}:\d{2})",
        ]

        # Try to find a complete transaction block
        amount = None
        for pattern in amount_patterns:
            m = re.search(pattern, text)
            if m:
                amount = Decimal(m.group(1).replace(",", ""))
                break

        if not amount:
            return transactions

        merchant = "未知商户"
        for pattern in merchant_patterns:
            m = re.search(pattern, text)
            if m:
                merchant = m.group(1).strip()
                break

        occurred_on = date.today()
        for pattern in date_patterns:
            m = re.search(pattern, text)
            if m:
                date_str = m.group(1).split()[0]
                try:
                    parts = re.split(r"[-/]", date_str)
                    if len(parts) == 3:
                        occurred_on = date(int(parts[0]), int(parts[1]), int(parts[2]))
                except (ValueError, IndexError):
                    pass
                break

        if since_date and occurred_on < since_date:
            return transactions

        # Determine direction from context
        direction = BillDirection.EXPENSE
        if any(kw in text for kw in ["退款", "收入", "到账", "收款", "转入"]):
            direction = BillDirection.INCOME

        transactions.append(RawTransaction(
            source_name=self.source_name,
            occurred_on=occurred_on,
            amount=amount,
            direction=direction,
            merchant_name=merchant,
            channel="alipay_email",
            note="",
            raw_data={"email_subject": text[:200]},
        ))

        return transactions
