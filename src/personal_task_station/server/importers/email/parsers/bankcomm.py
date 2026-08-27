from __future__ import annotations

import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

from personal_task_station.server.importers.base import ImportResult, RawTransaction
from personal_task_station.server.importers.email.client import FetchedEmail
from personal_task_station.server.importers.email.parser_base import EmailParserBase
from personal_task_station.shared.enums import BillDirection


class BankcommEmailParser(EmailParserBase):
    """Parser for Bank of Communications (交通银行) credit card email statements.

    Handles:
    - HTML notification emails (per-transaction alerts)
    - Excel attachments from App manual export
    """

    source_name = "bankcomm_email"
    sender_patterns = ["bankcomm.com", "95559@", "bocom.com.cn"]
    subject_patterns = ["交通银行", "信用卡", "交易提醒", "账单", "交行"]

    def parse(self, email: FetchedEmail, since_date: date | None = None,
              passwords: tuple[str, ...] = ()) -> ImportResult:
        result = ImportResult(source_name=self.source_name)

        # 1. Excel attachments (App manual export)
        for filename, payload in email.attachments:
            if filename.lower().endswith((".xlsx", ".xls")):
                transactions = self._parse_excel_attachment(payload, since_date)
                if transactions:
                    result.raw_transactions.extend(transactions)
                    return result
                result.errors.append(f"Excel attachment '{filename}' parsed 0 rows")

        # 2. HTML table
        if email.body_html:
            transactions = self._parse_html_table(email.body_html, since_date)
            if transactions:
                result.raw_transactions.extend(transactions)
                return result

        # 3. Plain text fallback
        text = email.body_text or ""
        if not text:
            result.errors.append("Empty email body")
            return result
        transactions = self._parse_text_format(text, since_date)
        result.raw_transactions.extend(transactions)
        return result

    # ------------------------------------------------------------------ #
    # Excel                                                                #
    # ------------------------------------------------------------------ #

    def _parse_excel_attachment(self, payload: bytes, since_date: date | None) -> list[RawTransaction]:
        try:
            import openpyxl
        except ImportError:
            return []

        transactions: list[RawTransaction] = []
        wb = openpyxl.load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) < 2:
                continue
            header_idx = None
            for i, row in enumerate(rows[:10]):
                row_text = "".join(str(c) for c in row if c is not None)
                if any(kw in row_text for kw in ["交易日期", "交易时间", "记账日期", "金额"]):
                    header_idx = i
                    break
            if header_idx is None:
                continue
            headers = [str(c).strip() if c is not None else "" for c in rows[header_idx]]
            col_map = self._map_headers(headers)
            for row in rows[header_idx + 1:]:
                cells = [str(c).strip() if c is not None else "" for c in row]
                if not any(cells):
                    continue
                try:
                    tx = self._row_to_transaction(cells, col_map)
                    if tx and (since_date is None or tx.occurred_on >= since_date):
                        transactions.append(tx)
                except Exception:
                    continue
        return transactions

    # ------------------------------------------------------------------ #
    # HTML table                                                           #
    # ------------------------------------------------------------------ #

    def _parse_html_table(self, html: str, since_date: date | None) -> list[RawTransaction]:
        soup = BeautifulSoup(html, "lxml")
        transactions: list[RawTransaction] = []
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
            if not any(kw in "".join(headers) for kw in ["交易", "金额", "商户", "日期"]):
                continue
            col_map = self._map_headers(headers)
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if len(cells) < 3:
                    continue
                try:
                    tx = self._row_to_transaction(cells, col_map)
                    if tx and (since_date is None or tx.occurred_on >= since_date):
                        transactions.append(tx)
                except Exception:
                    continue
        return transactions

    # ------------------------------------------------------------------ #
    # Plain text                                                           #
    # ------------------------------------------------------------------ #

    def _parse_text_format(self, text: str, since_date: date | None) -> list[RawTransaction]:
        transactions: list[RawTransaction] = []
        pattern = re.compile(
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})\s+(.+?)\s+([+-]?[\d,]+\.\d{2})",
            re.MULTILINE,
        )
        for match in pattern.finditer(text):
            date_str, desc, amt_str = match.groups()
            occurred_on = self._parse_date(date_str)
            if not occurred_on or (since_date and occurred_on < since_date):
                continue
            amt_str = amt_str.replace(",", "")
            direction = BillDirection.INCOME if amt_str.startswith("+") else BillDirection.EXPENSE
            amt_str = amt_str.lstrip("+-")
            try:
                amount = Decimal(amt_str)
                if amount > 0:
                    transactions.append(RawTransaction(
                        source_name=self.source_name,
                        occurred_on=occurred_on,
                        amount=amount,
                        direction=direction,
                        merchant_name=desc.strip(),
                        channel="bankcomm_email_text",
                        raw_data={"match": match.group(0)},
                    ))
            except InvalidOperation:
                continue
        return transactions

    # ------------------------------------------------------------------ #
    # Shared helpers                                                       #
    # ------------------------------------------------------------------ #

    def _map_headers(self, headers: list[str]) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for i, h in enumerate(headers):
            hl = h.lower()
            if any(kw in hl for kw in ["交易日期", "记账日期", "交易时间", "日期", "时间", "date"]):
                mapping.setdefault("date", i)
            elif any(kw in hl for kw in ["商户", "交易描述", "摘要", "说明", "merchant", "description"]):
                mapping.setdefault("merchant", i)
            elif any(kw in hl for kw in ["收入", "存入", "credit", "income"]):
                mapping.setdefault("income", i)
            elif any(kw in hl for kw in ["支出", "消费", "扣款", "debit", "expense"]):
                mapping.setdefault("expense", i)
            elif any(kw in hl for kw in ["金额", "交易金额", "amount"]):
                mapping.setdefault("amount", i)
            elif any(kw in hl for kw in ["卡号", "尾号", "card"]):
                mapping.setdefault("card", i)
        return mapping

    def _row_to_transaction(self, cells: list[str], col_map: dict[str, int]) -> RawTransaction | None:
        date_str = cells[col_map.get("date", 0)] if "date" in col_map else ""
        if not date_str:
            return None
        occurred_on = self._parse_date(date_str)
        if not occurred_on:
            return None

        amount = Decimal("0")
        direction = BillDirection.EXPENSE

        if "income" in col_map and "expense" in col_map:
            inc = cells[col_map["income"]].replace(",", "").replace("+", "").strip()
            exp = cells[col_map["expense"]].replace(",", "").replace("-", "").strip()
            if inc and inc not in ("-", ""):
                try:
                    amount = Decimal(inc)
                    direction = BillDirection.INCOME
                except InvalidOperation:
                    pass
            elif exp and exp not in ("-", ""):
                try:
                    amount = Decimal(exp)
                    direction = BillDirection.EXPENSE
                except InvalidOperation:
                    pass
        elif "amount" in col_map:
            amt_str = cells[col_map["amount"]].replace(",", "").strip()
            if amt_str.startswith("-") or amt_str.startswith("("):
                direction = BillDirection.EXPENSE
                amt_str = amt_str.lstrip("-").strip("()")
            elif amt_str.startswith("+"):
                direction = BillDirection.INCOME
                amt_str = amt_str[1:]
            try:
                amount = Decimal(amt_str)
            except InvalidOperation:
                return None
        else:
            return None

        if amount <= 0:
            return None

        merchant = cells[col_map["merchant"]] if "merchant" in col_map else "未知商户"
        card_last4 = ""
        if "card" in col_map:
            m = re.search(r"(\d{4})", cells[col_map["card"]])
            if m:
                card_last4 = m.group(1)

        return RawTransaction(
            source_name=self.source_name,
            occurred_on=occurred_on,
            amount=amount,
            direction=direction,
            merchant_name=merchant or "未知商户",
            channel="bankcomm_email",
            card_last4=card_last4,
            raw_data={"cells": cells},
        )

    def _parse_date(self, date_str: str) -> date | None:
        formats = [
            "%Y-%m-%d", "%Y/%m/%d", "%m-%d", "%m/%d",
            "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
            "%Y年%m月%d日", "%m月%d日",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                if dt.year == 1900:
                    dt = dt.replace(year=date.today().year)
                return dt.date()
            except ValueError:
                continue
        return None
