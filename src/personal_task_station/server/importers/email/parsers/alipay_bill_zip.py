"""Alipay monthly statement zip attachment parser.

支付宝「我的 → 账单 → 开具交易流水证明」及月度账单邮件会发送加密 zip，内含
GBK 编码 CSV，表头形如::

    交易号,商家订单号,交易创建时间,付款时间,最近修改时间,交易来源地,类型,
    交易对方,商品名称,金额（元）,收/支,交易状态,服务费（元）,成功退款（元）,备注,资金状态

Summary preamble/footer blocks without a valid 收/支 column value are skipped.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from personal_task_station.server.importers.base import ImportResult, RawTransaction
from personal_task_station.server.importers.email.attachments import extract_csv_members
from personal_task_station.server.importers.email.client import FetchedEmail
from personal_task_station.server.importers.email.parser_base import EmailParserBase
from personal_task_station.shared.enums import BillDirection


class AlipayBillZipParser(EmailParserBase):
    source_name = "alipay_bill_zip"
    sender_patterns = ["alipay.com"]
    subject_patterns = ["流水证明", "交易流水", "账单", "支付宝"]

    def can_parse(self, email: FetchedEmail) -> bool:
        sender_or_subject = super().can_parse(email)
        has_zip = any(name.lower().endswith(".zip") for name, _ in email.attachments)
        return sender_or_subject and has_zip

    def parse(self, email: FetchedEmail, since_date: date | None = None,
              passwords: tuple[str, ...] = ()) -> ImportResult:
        result = ImportResult(source_name=self.source_name)
        for filename, payload in email.attachments:
            if not filename.lower().endswith(".zip"):
                continue
            members, errors = extract_csv_members(payload, passwords)
            result.errors.extend(f"{filename}: {err}" for err in errors)
            for member_name, text in members:
                parsed = self._parse_csv(text, since_date)
                result.raw_transactions.extend(parsed)
        if not any(f.lower().endswith(".zip") for f, _ in email.attachments):
            result.errors.append("no zip attachment found")
        return result

    def _parse_csv(self, text: str, since_date: date | None) -> list[RawTransaction]:
        rows: list[RawTransaction] = []
        lines = text.splitlines()
        header_index = None
        for index, line in enumerate(lines):
            if "交易创建时间" in line and "收/支" in line:
                header_index = index
                break
        if header_index is None:
            return rows

        reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
        for row in reader:
            if row is None or not any((v or "").strip() for v in row.values()):
                continue
            occurred_raw = (row.get("交易创建时间") or "").strip()
            occurred_on = self._parse_datetime(occurred_raw)
            if occurred_on is None:
                continue
            direction_str = (row.get("收/支") or "").strip()
            if direction_str not in ("收入", "支出"):
                continue
            amount_key = next(
                (k for k in row.keys() if k and "金额" in k and "服务费" not in k and "退款" not in k),
                None,
            )
            amount = self._parse_amount(row.get(amount_key or ""))
            if amount is None:
                continue
            direction = BillDirection.INCOME if direction_str == "收入" else BillDirection.EXPENSE
            external_id = (row.get("交易号") or row.get("支付宝交易号") or "").strip()
            merchant = (row.get("交易对方") or "").strip() or "支付宝交易"
            product = (row.get("商品名称") or "").strip()
            tx_type = (row.get("类型") or "").strip()
            note = "; ".join(part for part in (product, tx_type) if part)
            rows.append(
                RawTransaction(
                    source_name=self.source_name,
                    occurred_on=occurred_on,
                    amount=amount,
                    direction=direction,
                    merchant_name=merchant,
                    channel="alipay",
                    note=note,
                    external_id=external_id,
                    raw_data={key: (value or "") for key, value in row.items()},
                )
            )
        return rows

    @staticmethod
    def _parse_amount(value: str | None) -> Decimal | None:
        if not value:
            return None
        cleaned = re.sub(r"[¥￥,\s]", "", value.strip())
        if not cleaned:
            return None
        try:
            return abs(Decimal(cleaned))
        except InvalidOperation:
            return None

    @staticmethod
    def _parse_datetime(value: str) -> date | None:
        value = value.strip()
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(value.split()[0], fmt).date()
            except ValueError:
                continue
        return None
