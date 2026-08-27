"""WeChat Pay monthly bill zip attachment parser.

WeChat「我 → 服务 → 钱包 → 账单 → 下载账单」sends an encrypted zip containing a
CSV member such as ``微信支付交易明细证明(...).csv``. Rows follow::

    交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号,商户单号,备注

Preamble/footer metadata lines are skipped by locating the header row.
Neutral transactions (收/支 == "/") are ignored.
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


class WechatBillZipParser(EmailParserBase):
    source_name = "wechat_bill_zip"
    sender_patterns = ["tenpay.com", "wechatpay"]
    subject_patterns = ["微信支付账单明细", "微信支付交易明细", "微信账单", "账单"]

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
                result.skipped_count += self._skipped
        if not any(f.lower().endswith(".zip") for f, _ in email.attachments):
            result.errors.append("no zip attachment found")
        return result

    _skipped = 0

    def _parse_csv(self, text: str, since_date: date | None) -> list[RawTransaction]:
        skipped = 0
        rows: list[RawTransaction] = []
        lines = text.splitlines()
        header_index = None
        for index, line in enumerate(lines):
            if ("交易时间" in line and "金额" in line) or (
                "交易时间" in line and "交易对方" in line
            ):
                header_index = index
                break
        if header_index is None:
            return rows

        reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
        for row in reader:
            if row is None or not any((v or "").strip() for v in row.values()):
                continue
            occurred_raw = (row.get("交易时间") or "").strip()
            occurred_on = self._parse_datetime(occurred_raw)
            if occurred_on is None:
                skipped += 1
                continue
            direction_str = (row.get("收/支") or "").strip()
            if direction_str not in ("收入", "支出"):
                skipped += 1
                continue
            amount = self._parse_amount(row.get("金额(元)") or row.get("金额（元）") or "")
            if amount is None:
                skipped += 1
                continue
            direction = BillDirection.INCOME if direction_str == "收入" else BillDirection.EXPENSE
            external_id = (row.get("交易单号") or "").strip()
            merchant = (row.get("交易对方") or "").strip() or "微信支付交易"
            product = (row.get("商品") or "").strip()
            pay_channel = (row.get("支付方式") or "").strip()
            note_parts = [part for part in (product,) if part]
            note = "; ".join(note_parts)
            rows.append(
                RawTransaction(
                    source_name=self.source_name,
                    occurred_on=occurred_on,
                    amount=amount,
                    direction=direction,
                    merchant_name=merchant,
                    channel=pay_channel,
                    card_last4="",
                    note=note,
                    external_id=external_id,
                    raw_data={key: (value or "") for key, value in row.items()},
                )
            )
        self._skipped = skipped
        return rows

    @staticmethod
    def _parse_amount(value: str) -> Decimal | None:
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
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return None
