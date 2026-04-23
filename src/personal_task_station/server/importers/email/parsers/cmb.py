from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from bs4 import BeautifulSoup

from personal_task_station.server.importers.base import ImportResult, RawTransaction
from personal_task_station.server.importers.email.client import FetchedEmail
from personal_task_station.server.importers.email.parser_base import EmailParserBase
from personal_task_station.shared.enums import BillDirection


class CmbEmailParser(EmailParserBase):
    """Parser for China Merchants Bank (招商银行) email statements.

    Handles HTML email statements that contain transaction tables.
    Typical email from: creditcard@email.cmbchina.com or cmb@email.cmbchina.com
    """

    source_name = "cmb_email"
    sender_patterns = ["cmbchina.com", "creditcard@", "cmb@"]
    subject_patterns = ["信用卡对账单", "账务明细", "交易提醒", "招商银行"]

    def parse(self, email: FetchedEmail, since_date: date | None = None) -> ImportResult:
        result = ImportResult(source_name=self.source_name)
        text = self._extract_text(email)
        if not text:
            result.errors.append("Empty email body")
            return result

        # Try to parse HTML tables first
        if email.body_html:
            transactions = self._parse_html_table(email.body_html, since_date)
            if transactions:
                result.raw_transactions.extend(transactions)
                return result

        # Fallback: parse text format
        transactions = self._parse_text_format(text, since_date)
        result.raw_transactions.extend(transactions)
        return result

    def _parse_html_table(self, html: str, since_date: date | None) -> list[RawTransaction]:
        soup = BeautifulSoup(html, "lxml")
        transactions: list[RawTransaction] = []

        # Look for tables that contain transaction data
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            # Detect if this is a transaction table by headers
            header_row = rows[0]
            headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
            header_text = "".join(headers)

            if not any(kw in header_text for kw in ["交易", "金额", "商户", "日期", "时间", "支出", "收入"]):
                continue

            # Map headers to fields
            col_map = self._map_headers(headers)

            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) < 3:
                    continue

                cell_texts = [cell.get_text(strip=True) for cell in cells]
                try:
                    tx = self._row_to_transaction(cell_texts, col_map)
                    if tx and (since_date is None or tx.occurred_on >= since_date):
                        transactions.append(tx)
                except Exception:
                    continue

        return transactions

    def _map_headers(self, headers: list[str]) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for i, h in enumerate(headers):
            h_lower = h.lower()
            if any(kw in h_lower for kw in ["日期", "时间", "date", "time"]):
                mapping["date"] = i
            elif any(kw in h_lower for kw in ["商户", "交易对手", "对方", "merchant", "description", "摘要", "说明"]):
                mapping["merchant"] = i
            elif any(kw in h_lower for kw in ["收入", "存入", "收入金额", "credit", "income"]):
                mapping["income"] = i
            elif any(kw in h_lower for kw in ["支出", "支取", "支出金额", "扣款", "debit", "expense"]):
                mapping["expense"] = i
            elif any(kw in h_lower for kw in ["金额", "amount", "交易金额"]):
                mapping["amount"] = i
            elif any(kw in h_lower for kw in ["卡号", "尾号", "card", "账号"]):
                mapping["card"] = i
            elif any(kw in h_lower for kw in ["备注", "note", "附言", "用途"]):
                mapping["note"] = i
        return mapping

    def _row_to_transaction(self, cells: list[str], col_map: dict[str, int]) -> RawTransaction | None:
        # Try to get date
        date_str = cells[col_map.get("date", 0)] if "date" in col_map else ""
        if not date_str:
            return None

        # Parse date - try multiple formats
        occurred_on = self._parse_date(date_str)
        if not occurred_on:
            return None

        # Try to get amount
        amount = Decimal("0")
        direction = BillDirection.EXPENSE

        if "income" in col_map and "expense" in col_map:
            income_str = cells[col_map["income"]].replace(",", "").replace("+", "").strip()
            expense_str = cells[col_map["expense"]].replace(",", "").replace("-", "").strip()
            if income_str and income_str != "-":
                amount = Decimal(income_str)
                direction = BillDirection.INCOME
            elif expense_str and expense_str != "-":
                amount = Decimal(expense_str)
                direction = BillDirection.EXPENSE
        elif "amount" in col_map:
            amt_str = cells[col_map["amount"]].replace(",", "").strip()
            # Detect sign
            if amt_str.startswith("-") or amt_str.startswith("("):
                direction = BillDirection.EXPENSE
                amt_str = amt_str.replace("-", "").replace("(", "").replace(")", "")
            elif amt_str.startswith("+"):
                direction = BillDirection.INCOME
                amt_str = amt_str[1:]
            amount = Decimal(amt_str)
        else:
            return None

        if amount <= 0:
            return None

        merchant = ""
        if "merchant" in col_map:
            merchant = cells[col_map["merchant"]]

        card_last4 = ""
        if "card" in col_map:
            card_text = cells[col_map["card"]]
            match = re.search(r"(\d{4})", card_text)
            if match:
                card_last4 = match.group(1)

        note = ""
        if "note" in col_map:
            note = cells[col_map["note"]]

        return RawTransaction(
            source_name=self.source_name,
            occurred_on=occurred_on,
            amount=amount,
            direction=direction,
            merchant_name=merchant or "未知商户",
            channel="cmb_email",
            card_last4=card_last4,
            note=note,
            raw_data={"cells": cells},
        )

    def _parse_date(self, date_str: str) -> date | None:
        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%m-%d",
            "%m/%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%m月%d日",
            "%Y年%m月%d日",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                # If year is missing, assume current year
                if dt.year == 1900:
                    dt = dt.replace(year=date.today().year)
                return dt.date()
            except ValueError:
                continue
        return None

    def _parse_text_format(self, text: str, since_date: date | None) -> list[RawTransaction]:
        """Parse plain-text statement format."""
        transactions: list[RawTransaction] = []
        # Match lines like: 2026-04-23 商户名称 -123.45
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
            direction = BillDirection.EXPENSE
            if amt_str.startswith("+"):
                direction = BillDirection.INCOME
                amt_str = amt_str[1:]
            elif amt_str.startswith("-"):
                amt_str = amt_str[1:]
            try:
                amount = Decimal(amt_str)
                if amount > 0:
                    transactions.append(RawTransaction(
                        source_name=self.source_name,
                        occurred_on=occurred_on,
                        amount=amount,
                        direction=direction,
                        merchant_name=desc.strip(),
                        channel="cmb_email_text",
                        raw_data={"match": match.group(0)},
                    ))
            except Exception:
                continue
        return transactions
