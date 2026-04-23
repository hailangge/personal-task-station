from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from personal_task_station.server.importers.base import ImportResult, RawTransaction
from personal_task_station.server.importers.email.client import FetchedEmail
from personal_task_station.server.importers.email.parser_base import EmailParserBase
from personal_task_station.shared.enums import BillDirection


class GenericNotificationParser(EmailParserBase):
    """Fallback parser for any Chinese e-commerce / payment notification email.

    Uses broad regex patterns to extract transaction info from common notification formats.
    This parser is intentionally lenient and should be registered last in the parser chain.
    """

    source_name = "email_generic"
    sender_patterns = []  # Matches anything
    subject_patterns = []  # Matches anything

    def can_parse(self, email: FetchedEmail) -> bool:
        # Always accept as fallback
        return True

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

        # Try to find amount with Chinese currency symbols
        amount_match = re.search(r"[¥￥]\s*([\d,]+\.\d{2})", text)
        if not amount_match:
            # Try without currency symbol but with "元"
            amount_match = re.search(r"([\d,]+\.\d{2})\s*元", text)
        if not amount_match:
            return transactions

        amount = Decimal(amount_match.group(1).replace(",", ""))

        # Try to find merchant/description
        merchant = "未知商户"
        for pattern in [
            r"(?:商户|商家|店铺|卖家|交易对方)[：:]\s*(.+?)(?:\n|，|,|$|<)",
            r"(?:商品|订单)[：:]\s*(.+?)(?:\n|，|,|$|<)",
        ]:
            m = re.search(pattern, text)
            if m:
                merchant = m.group(1).strip()[:50]
                break

        # Try to find date
        occurred_on = date.today()
        for pattern in [
            r"(?:时间|日期)[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2})",
            r"(\d{4}年\d{1,2}月\d{1,2}日)",
        ]:
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

        # Determine direction from keywords
        direction = BillDirection.EXPENSE
        if any(kw in text for kw in ["退款", "收入", "到账", "收款", "转入", "入账"]):
            direction = BillDirection.INCOME

        # Try to determine a more specific source from the text
        source = self.source_name
        if "支付宝" in text or "alipay" in text.lower():
            source = "alipay_email_generic"
        elif "微信" in text or "wechat" in text.lower() or "微信支付" in text:
            source = "wechat_email_generic"
        elif "京东" in text or "jd.com" in text.lower():
            source = "jd_email_generic"
        elif "淘宝" in text or "天猫" in text or "taobao" in text.lower() or "tmall" in text.lower():
            source = "taobao_email_generic"
        elif "拼多多" in text or "pinduoduo" in text.lower():
            source = "pdd_email_generic"
        elif "招行" in text or "招商银行" in text or "cmb" in text.lower():
            source = "cmb_email_generic"

        transactions.append(RawTransaction(
            source_name=source,
            occurred_on=occurred_on,
            amount=amount,
            direction=direction,
            merchant_name=merchant,
            channel="email_generic",
            raw_data={"source_detected": source},
        ))
        return transactions
