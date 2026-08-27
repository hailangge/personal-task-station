"""Electronic invoice PDF attachment parser (电子发票).

Invoices delivered by JD/Tmall/banks arrive as PDF attachments. Uses
``pdfplumber`` (already part of the ``server`` extra) to extract text and then
parses key fields with regexes. One invoice maps to one RawTransaction whose
external id is the invoice number, making ingestion naturally idempotent.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime
from decimal import Decimal

from personal_task_station.server.importers.base import ImportResult, RawTransaction
from personal_task_station.server.importers.email.client import FetchedEmail
from personal_task_station.server.importers.email.parser_base import EmailParserBase
from personal_task_station.shared.enums import BillDirection


class InvoicePdfEmailParser(EmailParserBase):
    source_name = "invoice_pdf"
    sender_patterns = []
    subject_patterns = ["发票", "电子发票", "invoice"]

    def can_parse(self, email: FetchedEmail) -> bool:
        subject_match = any(pattern in email.subject for pattern in self.subject_patterns)
        has_pdf = any(name.lower().endswith(".pdf") for name, _ in email.attachments)
        return subject_match and has_pdf

    def parse(self, email: FetchedEmail, since_date: date | None = None,
              passwords: tuple[str, ...] = ()) -> ImportResult:
        del passwords
        result = ImportResult(source_name=self.source_name)
        pdf_payloads = [
            (name, payload)
            for name, payload in email.attachments
            if name.lower().endswith(".pdf")
        ]
        if not pdf_payloads:
            result.errors.append("no pdf attachment found")
            return result

        for filename, payload in pdf_payloads:
            fields = self._extract_pdf_text(payload)
            if fields is None:
                result.errors.append(f"{filename}: pdfplumber not available; run pip install '.[server]'")
                continue
            transaction = self._transaction_from_text(fields)
            if transaction is None:
                result.errors.append(f"{filename}: could not find invoice amount/number")
                continue
            if since_date and transaction.occurred_on < since_date:
                result.skipped_count += 1
                continue
            result.raw_transactions.append(transaction)

        return result

    @staticmethod
    def _extract_pdf_text(payload: bytes) -> str | None:
        try:
            import pdfplumber
        except ImportError:
            return None
        chunks: list[str] = []
        with pdfplumber.open(io.BytesIO(payload)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                chunks.append(text)
        return "\n".join(chunks)

    def _transaction_from_text(self, text: str) -> RawTransaction | None:
        number_match = re.search(r"发票号码\s*[：:]\s*(\d{8,30})", text)
        amount_match = re.search(r"价税合计[^¥￥\n]*[¥￥]\s*([\d,]+\.\d{2})", text) or re.search(
            r"[（(]小写[)）]\s*[¥￥]?\s*([\d,]+\.\d{2})", text
        )
        cn_date_match = re.search(r"开票日期\s*[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", text)
        iso_date_match = re.search(r"开票日期\s*[：:]\s*(\d{4}-\d{1,2}-\d{1,2})", text)
        seller_matches = re.findall(r"名\s*称\s*[：:]\s*(\S+)", text)
        title_line = next(
            (line for line in text.splitlines() if "发票" in line and "%" not in line),
            "",
        )

        if not amount_match or not number_match:
            return None

        amount = Decimal(amount_match.group(1).replace(",", ""))
        if amount < 0:
            amount = -amount

        occurred_on = date.today()
        if cn_date_match:
            try:
                occurred_on = date(int(cn_date_match.group(1)), int(cn_date_match.group(2)), int(cn_date_match.group(3)))
            except ValueError:
                pass
        elif iso_date_match:
            try:
                occurred_on = datetime.strptime(iso_date_match.group(1), "%Y-%m-%d").date()
            except ValueError:
                pass

        seller = seller_matches[-1].strip() if seller_matches else ""
        invoice_number = number_match.group(1)

        return RawTransaction(
            source_name=self.source_name,
            occurred_on=occurred_on,
            amount=amount,
            direction=BillDirection.EXPENSE,
            merchant_name=seller or title_line.strip() or "电子发票",
            channel="invoice_pdf",
            note=f"发票号码 {invoice_number}",
            external_id=f"invoice:{invoice_number}",
            raw_data={"title": title_line, "seller": seller},
        )
