from __future__ import annotations

import hashlib
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

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

    def parse(self, email: FetchedEmail, since_date: date | None = None,
              passwords: tuple[str, ...] = ()) -> ImportResult:
        result = ImportResult(source_name=self.source_name)

        # 1. PDF attachment (monthly statement from CMB email)
        for filename, payload in email.attachments:
            fname = self._decode_filename(filename)
            if fname.lower().endswith(".pdf"):
                transactions = self._parse_pdf_attachment(payload, since_date)
                if transactions:
                    result.raw_transactions.extend(transactions)
                    return result
                result.errors.append(f"PDF attachment '{fname}' parsed 0 rows")

        # 2. Excel attachment (App manual export)
        for filename, payload in email.attachments:
            fname = self._decode_filename(filename)
            if fname.lower().endswith((".xlsx", ".xls")):
                transactions = self._parse_excel_attachment(payload, since_date)
                if transactions:
                    result.raw_transactions.extend(transactions)
                    return result
                result.errors.append(f"Excel attachment '{fname}' parsed 0 rows")

        # 3. HTML table (inline notification email)
        if email.body_html:
            transactions = self._parse_html_table(email.body_html, since_date)
            if len(transactions) < 3:
                # Layout-heavy statements (nested/CSS-hacked tables) defeat
                # generic table parsing; fall back to the statement line scan.
                line_txs = self._parse_statement_lines(email.body_html, since_date)
                if len(line_txs) > len(transactions):
                    transactions = line_txs
            if transactions:
                result.raw_transactions.extend(transactions)
                return result

        # 4. Fallback: plain text
        text = self._extract_text(email)
        if not text:
            result.errors.append("Empty email body")
            return result
        transactions = self._parse_text_format(text, since_date)
        result.raw_transactions.extend(transactions)
        return result

    def _decode_filename(self, filename: str) -> str:
        from email.header import decode_header
        parts = decode_header(filename)
        result = []
        for p, cs in parts:
            if isinstance(p, bytes):
                try:
                    result.append(p.decode(cs or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    result.append(p.decode("utf-8", errors="replace"))
            else:
                result.append(str(p))
        return "".join(result)

    def _parse_pdf_attachment(self, payload: bytes, since_date: date | None) -> list[RawTransaction]:
        try:
            import io
            import pdfplumber
        except ImportError:
            return []

        transactions: list[RawTransaction] = []
        # CMB PDF columns: 交易日, 记账日, 交易摘要, 人民币金额, 卡号末四位, 交易地金额
        with pdfplumber.open(io.BytesIO(payload)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    for row in table:
                        if not row or len(row) < 4:
                            continue
                        # Skip header rows
                        cell0 = str(row[0] or "").strip()
                        if not cell0 or any(kw in cell0 for kw in ["交易日", "Trans", "Date"]):
                            continue
                        # row: [trans_date, post_date, description, rmb_amount, card_last4, orig_amount]
                        trans_date_str = cell0
                        description = str(row[2] or "").strip() if len(row) > 2 else ""
                        amount_str = str(row[3] or "").strip() if len(row) > 3 else ""
                        card_last4 = str(row[4] or "").strip() if len(row) > 4 else ""

                        if not trans_date_str or not amount_str:
                            continue

                        # Parse date (format: MM/DD)
                        occurred_on = self._parse_date(trans_date_str)
                        if not occurred_on:
                            continue
                        if since_date and occurred_on < since_date:
                            continue

                        # Parse amount
                        amt_clean = amount_str.replace(",", "").replace(" ", "")
                        direction = BillDirection.EXPENSE
                        if amt_clean.startswith("-"):
                            direction = BillDirection.INCOME  # repayment / credit
                            amt_clean = amt_clean[1:]
                        try:
                            amount = Decimal(amt_clean)
                        except InvalidOperation:
                            continue
                        if amount <= 0:
                            continue

                        transactions.append(RawTransaction(
                            source_name=self.source_name,
                            occurred_on=occurred_on,
                            amount=amount,
                            direction=direction,
                            merchant_name=description or "未知商户",
                            channel="cmb_pdf",
                            card_last4=card_last4,
                            raw_data={"row": [str(c) for c in row]},
                        ))
        return transactions

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
            # Find header row (first row containing date/amount keywords)
            header_idx = None
            for i, row in enumerate(rows[:10]):
                row_text = "".join(str(c) for c in row if c is not None)
                if any(kw in row_text for kw in ["交易时间", "记账时间", "交易日期", "金额", "交易金额"]):
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
            # first-wins: the earliest matching column keeps the slot so that
            # e.g. 交易日期 wins over the later 记账日期 column.
            if any(kw in h_lower for kw in ["日期", "时间", "date", "time"]):
                mapping.setdefault("date", i)
            elif any(kw in h_lower for kw in ["商户", "交易对手", "对方", "merchant", "description", "摘要", "说明"]):
                mapping.setdefault("merchant", i)
            elif any(kw in h_lower for kw in ["收入", "存入", "收入金额", "credit", "income"]):
                mapping.setdefault("income", i)
            elif any(kw in h_lower for kw in ["支出", "支取", "支出金额", "扣款", "debit", "expense"]):
                mapping.setdefault("expense", i)
            elif any(kw in h_lower for kw in ["金额", "amount", "交易金额"]):
                mapping.setdefault("amount", i)
            elif any(kw in h_lower for kw in ["卡号", "尾号", "card", "账号"]):
                mapping.setdefault("card", i)
            elif any(kw in h_lower for kw in ["备注", "note", "附言", "用途"]):
                mapping.setdefault("note", i)
        return mapping

    def _row_to_transaction(self, cells: list[str], col_map: dict[str, int]) -> RawTransaction | None:
        joined = " ".join(cells)
        if "<" in joined and ">" in joined:
            # Leftover HTML markup means this is a layout artifact row.
            return None
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
            income_str = self._clean_amount(cells[col_map["income"]]).lstrip("+")
            expense_str = self._clean_amount(cells[col_map["expense"]]).lstrip("-").lstrip("(").rstrip(")")
            try:
                if income_str and income_str != "-":
                    amount = Decimal(income_str)
                    direction = BillDirection.INCOME
                elif expense_str and expense_str != "-":
                    amount = Decimal(expense_str)
                    direction = BillDirection.EXPENSE
            except InvalidOperation:
                return None
        elif "amount" in col_map:
            amt_str = self._clean_amount(cells[col_map["amount"]])
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

    def _parse_statement_lines(self, html: str, since_date: date | None) -> list[RawTransaction]:
        """Scan flattened statement text for per-transaction line groups.

        CMB monthly statements render each transaction as a fixed line group
        (type / MMDD / MMDD / merchant / ``¥`` amount / card tail / country /
        original amount); the type cell uses rowspan so it only appears once
        per group. Anchoring on the ``¥`` amount line and looking back three
        lines recovers every group even when table parsing fails.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:  # pragma: no cover - bs4/lxml are server deps
            return []

        lines = [ln.strip() for ln in BeautifulSoup(html, "lxml").get_text("\n").splitlines()]
        lines = [ln for ln in lines if ln]

        period_m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})\s*-\s*(\d{4})/(\d{1,2})/(\d{1,2})", html)
        if period_m:
            period_start = date(int(period_m.group(1)), int(period_m.group(2)), int(period_m.group(3)))
            period_end = date(int(period_m.group(4)), int(period_m.group(5)), int(period_m.group(6)))
        else:
            period_start = None
            period_end = None

        transactions: list[RawTransaction] = []
        current_type = "消费"
        for i, line in enumerate(lines):
            amt_m = self._YEN_AMOUNT.match(line)
            if not amt_m or i < 3:
                continue
            if not (self._MMDD.match(lines[i - 3]) and self._MMDD.match(lines[i - 2])):
                continue
            merchant = lines[i - 1]
            if not merchant or merchant.startswith("¥") or self._MMDD.match(merchant):
                continue

            for back in range(i - 3, max(-1, i - 10), -1):
                if lines[back] in self._TX_TYPES:
                    current_type = lines[back]
                    break

            mm, dd = int(lines[i - 3][:2]), int(lines[i - 3][2:])
            if period_start is not None:
                # Interpret MMDD inside the statement period (handles annual
                # rollover); lines outside the period are installment/future
                # deduction plans, not real transactions.
                year = period_start.year
                occurred_on = date(year, mm, dd)
                if occurred_on < period_start:
                    occurred_on = date(year + 1, mm, dd)
                if not (period_start <= occurred_on <= period_end):
                    continue
            else:
                occurred_on = self._resolve_mmdd_date(mm, dd)
            if since_date and occurred_on < since_date:
                continue

            raw_amount = Decimal(amt_m.group(1).replace(",", ""))
            direction = (
                BillDirection.INCOME
                if raw_amount < 0 or current_type in ("还款", "退货", "退款")
                else BillDirection.EXPENSE
            )
            amount = abs(raw_amount)
            if amount <= 0:
                # Zero-amount rows are things like annual-fee progress markers.
                continue

            card_last4 = lines[i + 1] if i + 1 < len(lines) and self._MMDD.match(lines[i + 1]) else ""
            stable = f"{occurred_on.isoformat()}|{merchant}|{amount}|{current_type}|{card_last4}"
            external_id = "cmb:" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]

            transactions.append(
                RawTransaction(
                    source_name=self.source_name,
                    occurred_on=occurred_on,
                    amount=amount,
                    direction=direction,
                    merchant_name=merchant,
                    channel="cmb_email_lines",
                    card_last4=card_last4[:4],
                    note=current_type,
                    external_id=external_id,
                    raw_data={"statement_lines": lines[max(0, i - 3) : i + 2]},
                )
            )
        return transactions

    @staticmethod
    def _resolve_mmdd_date(mm: int, dd: int) -> date:
        """Resolve a bare MMDD to a full date when no statement period exists."""
        today = date.today()
        try:
            candidate = date(today.year, mm, dd)
        except ValueError:
            return today
        if candidate > today:
            candidate = date(today.year - 1, mm, dd)
        return candidate

    _TX_TYPES = ("消费", "还款", "退货", "退款", "预借现金", "分期", "费用", "调整", "其他", "网上支付")
    _YEN_AMOUNT = re.compile(r"^¥\s*(-?[\d,]+\.\d{2})$")
    _MMDD = re.compile(r"^\d{4}$")

    @classmethod
    def _clean_amount(cls, text: str) -> str:
        """Normalize a table amount cell: strip currency codes/symbols/commas."""
        cleaned = (text or "").strip().replace(",", "")
        cleaned = cls._CURRENCY_PREFIX.sub("", cleaned)
        cleaned = cleaned.replace("¥", "").replace("￥", "").replace("$", "")
        return cleaned.strip()

    _CURRENCY_PREFIX = re.compile(r"^(CNY|JPY|USD|EUR|GBP|HKD|RMB)\s*", re.IGNORECASE)

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
