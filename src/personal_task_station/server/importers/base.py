from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from personal_task_station.shared.enums import BillDirection


@dataclass
class RawTransaction:
    source_name: str
    occurred_on: date
    amount: Decimal
    direction: BillDirection
    merchant_name: str
    channel: str = ""
    card_last4: str = ""
    note: str = ""
    external_id: str = ""
    raw_data: dict = field(default_factory=dict)


@dataclass
class ImportResult:
    source_name: str
    raw_transactions: list[RawTransaction] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped_count: int = 0


class TransactionImporter(Protocol):
    source_name: str

    def import_data(self, data: bytes | str, **kwargs) -> ImportResult:
        ...


class CsvImporter:
    """Generic CSV importer that maps columns via a field map."""

    def __init__(self, source_name: str, field_map: dict[str, str], date_format: str = "%Y-%m-%d"):
        self.source_name = source_name
        self.field_map = field_map
        self.date_format = date_format

    def import_data(self, data: bytes | str, **kwargs) -> ImportResult:
        result = ImportResult(source_name=self.source_name)
        text = data.decode("utf-8-sig") if isinstance(data, bytes) else data
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            try:
                tx = self._parse_row(row)
                if tx:
                    result.raw_transactions.append(tx)
            except Exception as exc:
                result.errors.append(str(exc))
                result.skipped_count += 1
        return result

    def _parse_row(self, row: dict[str, str]) -> RawTransaction | None:
        fm = self.field_map
        amount_str = row.get(fm.get("amount", "amount"), "").strip()
        if not amount_str:
            return None
        amount = Decimal(amount_str.replace(",", ""))
        direction = BillDirection.EXPENSE
        if amount < 0:
            amount = -amount
            direction = BillDirection.INCOME
        date_str = row.get(fm.get("date", "date"), "").strip()
        occurred_on = datetime.strptime(date_str, self.date_format).date() if date_str else date.today()
        merchant = row.get(fm.get("merchant", "merchant"), "").strip()
        if not merchant:
            merchant = row.get(fm.get("description", "description"), "").strip()
        return RawTransaction(
            source_name=self.source_name,
            occurred_on=occurred_on,
            amount=amount,
            direction=direction,
            merchant_name=merchant,
            channel=row.get(fm.get("channel", "channel"), "").strip(),
            card_last4=row.get(fm.get("card_last4", "card_last4"), "").strip(),
            note=row.get(fm.get("note", "note"), "").strip(),
            external_id=row.get(fm.get("external_id", "external_id"), "").strip(),
            raw_data=dict(row),
        )
