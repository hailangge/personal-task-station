from __future__ import annotations

import csv
import io
import re
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from personal_task_station.server.services.classifiers import (
    BaseTransactionClassifier,
    RuleBasedClassifier,
    build_classifier,
)
from personal_task_station.shared.enums import BillDirection, ImportJobStatus, MergeStatus
from personal_task_station.shared.models import (
    AuditLog,
    BillImportJob,
    MergedTransaction,
    MergedTransactionMember,
    ModelCallLog,
    NormalizedTransaction,
    RawTransaction,
)
from personal_task_station.shared.schemas import MonthlySummary


class BillingService:
    FIELD_ALIASES = {
        "occurred_on": ("date", "transaction_time", "time", "交易时间", "交易日期"),
        "amount": ("amount", "money", "transaction_amount", "金额", "实付金额"),
        "direction": ("direction", "type", "收支方向", "收支类型"),
        "merchant_name": ("merchant", "counterparty", "name", "交易对手", "商户", "merchant_name"),
        "source_name": ("source", "channel", "渠道", "platform", "来源"),
        "external_id": ("order_id", "transaction_id", "流水号", "订单号", "id"),
        "note": ("note", "remark", "备注", "memo"),
        "card_last4": ("card_last4", "last4", "卡号尾号"),
    }

    def __init__(self, session: Session, classifier: BaseTransactionClassifier | None = None):
        self.session = session
        self.classifier = classifier or build_classifier()

    def import_csv_bytes(self, *, source_name: str, filename: str, content: bytes) -> BillImportJob:
        job = BillImportJob(source_name=source_name, filename=filename, logs=[{"stage": "created"}])
        self.session.add(job)
        self.session.flush()
        try:
            rows = self._parse_table(content)
            raw_records: list[RawTransaction] = []
            normalized_records: list[NormalizedTransaction] = []
            for row_number, row in enumerate(rows, start=1):
                raw_record = RawTransaction(
                    import_job_id=job.id,
                    row_number=row_number,
                    source_name=source_name,
                    raw_data=row,
                    original_reference=str(self._extract_value(row, "external_id")),
                )
                self.session.add(raw_record)
                raw_records.append(raw_record)
                normalized_payload = self._normalize_row(row, source_name)
                normalized_record = NormalizedTransaction(
                    import_job_id=job.id,
                    raw_transaction=raw_record,
                    **normalized_payload,
                )
                self.session.add(normalized_record)
                normalized_records.append(normalized_record)
            self.session.flush()

            job.raw_count = len(raw_records)
            job.normalized_count = len(normalized_records)
            job.status = ImportJobStatus.COMPLETED
            job.logs = job.logs + [{"stage": "normalized", "count": len(normalized_records)}]
            self.rebuild_merged_transactions()
            merged_count = self.session.scalar(
                select(func.count()).select_from(MergedTransaction).where(MergedTransaction.is_active)
            )
            job.merged_count = int(merged_count or 0)
            self._record_audit(
                "billing.import_completed",
                "bill_import_job",
                str(job.id),
                {"source_name": source_name, "filename": filename, "rows": len(rows)},
            )
        except Exception as exc:
            job.status = ImportJobStatus.FAILED
            job.error_message = str(exc)
            job.logs = job.logs + [{"stage": "failed", "error": str(exc)}]
            self._record_audit(
                "billing.import_failed",
                "bill_import_job",
                str(job.id),
                {"error": str(exc)},
            )
            raise
        return job

    def reanalyze(self, import_job_id: int | None = None) -> None:
        stmt = select(NormalizedTransaction)
        if import_job_id is not None:
            stmt = stmt.where(NormalizedTransaction.import_job_id == import_job_id)
        for transaction in self.session.scalars(stmt):
            self._apply_classification(transaction)
            if transaction.merge_status == MergeStatus.MERGED:
                transaction.merge_status = MergeStatus.UNMERGED
        self.rebuild_merged_transactions()
        self._record_audit(
            "billing.reanalyzed",
            "billing",
            str(import_job_id or "all"),
            {"import_job_id": import_job_id},
        )

    def list_import_jobs(self) -> list[BillImportJob]:
        return list(self.session.scalars(select(BillImportJob).order_by(BillImportJob.created_at.desc())).all())

    def list_transactions(
        self,
        *,
        month: str | None = None,
        source_name: str | None = None,
        category: str | None = None,
        card_last4: str | None = None,
        amount_min: Decimal | None = None,
        amount_max: Decimal | None = None,
    ) -> list[NormalizedTransaction]:
        stmt = select(NormalizedTransaction).order_by(
            NormalizedTransaction.occurred_on.desc(),
            NormalizedTransaction.id.desc(),
        )
        if month:
            stmt = stmt.where(func.strftime("%Y-%m", NormalizedTransaction.occurred_on) == month)
        if source_name:
            stmt = stmt.where(NormalizedTransaction.source_name == source_name)
        if category:
            stmt = stmt.where(NormalizedTransaction.category_final == category)
        if card_last4:
            stmt = stmt.where(NormalizedTransaction.card_last4 == card_last4)
        if amount_min is not None:
            stmt = stmt.where(NormalizedTransaction.amount >= amount_min)
        if amount_max is not None:
            stmt = stmt.where(NormalizedTransaction.amount <= amount_max)
        return list(self.session.scalars(stmt).all())

    def list_duplicates(self) -> list[MergedTransaction]:
        stmt = (
            select(MergedTransaction)
            .where(MergedTransaction.is_active, MergedTransaction.duplicate_count > 0)
            .order_by(MergedTransaction.occurred_on.desc())
        )
        return list(self.session.scalars(stmt).all())

    def undo_merge(self, merged_transaction_id: int) -> None:
        merged = self.session.get(MergedTransaction, merged_transaction_id)
        if not merged or not merged.is_active:
            raise ValueError(f"Merged transaction {merged_transaction_id} not found")
        memberships = list(merged.members)
        merged.is_active = False
        self.session.flush()
        for member in memberships:
            member.normalized_transaction.merge_status = MergeStatus.UNDONE
        self.rebuild_merged_transactions()
        self._record_audit(
            "billing.merge_undone",
            "merged_transaction",
            str(merged_transaction_id),
            {"member_count": len(memberships)},
        )

    def list_model_calls(self, limit: int = 100) -> list[ModelCallLog]:
        stmt = select(ModelCallLog).order_by(ModelCallLog.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt).all())

    def monthly_summary(self, year: int, month: int) -> MonthlySummary:
        month_key = f"{year:04d}-{month:02d}"
        stmt = (
            select(MergedTransaction)
            .where(MergedTransaction.is_active)
            .options(selectinload(MergedTransaction.members).selectinload(MergedTransactionMember.normalized_transaction))
            .order_by(MergedTransaction.occurred_on.desc())
        )
        transactions = [item for item in self.session.scalars(stmt).all() if item.occurred_on.strftime("%Y-%m") == month_key]

        total_expense = Decimal("0.00")
        total_income = Decimal("0.00")
        by_category: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        by_source: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        by_account: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        duplicates: list[MergedTransaction] = []
        anomalies: list[MergedTransaction] = []

        for transaction in transactions:
            amount = Decimal(str(transaction.amount))
            if transaction.direction == BillDirection.EXPENSE:
                total_expense += abs(amount)
                by_category[transaction.category or "other"] += abs(amount)
                by_source[transaction.source_name or "unknown"] += abs(amount)
                account_key = self._account_key(transaction)
                by_account[account_key] += abs(amount)
                if abs(amount) >= Decimal("1000"):
                    anomalies.append(transaction)
            else:
                total_income += abs(amount)
            if transaction.duplicate_count > 0:
                duplicates.append(transaction)

        return MonthlySummary(
            month=month_key,
            total_expense=total_expense,
            total_income=total_income,
            by_category=dict(sorted(by_category.items())),
            by_source=dict(sorted(by_source.items())),
            by_account=dict(sorted(by_account.items())),
            duplicates=duplicates,
            anomalies=anomalies,
        )

    def rebuild_merged_transactions(self) -> None:
        active_merged_ids = select(MergedTransaction.id).where(MergedTransaction.is_active)
        self.session.execute(delete(MergedTransactionMember).where(MergedTransactionMember.merged_transaction_id.in_(active_merged_ids)))
        self.session.execute(delete(MergedTransaction).where(MergedTransaction.is_active))
        self.session.flush()

        transactions = list(
            self.session.scalars(
                select(NormalizedTransaction).order_by(NormalizedTransaction.occurred_on, NormalizedTransaction.id)
            ).all()
        )
        grouped: dict[str, list[NormalizedTransaction]] = defaultdict(list)
        for transaction in transactions:
            if transaction.merge_status == MergeStatus.UNDONE:
                grouped[f"manual:{transaction.id}"].append(transaction)
            else:
                grouped[transaction.dedupe_key].append(transaction)

        for group_key, members in grouped.items():
            canonical = members[0]
            if group_key.startswith("manual:"):
                duplicate_count = 0
            else:
                duplicate_count = max(0, len(members) - 1)
            category = self._dominant_category(members)
            merged = MergedTransaction(
                occurred_on=canonical.occurred_on,
                amount=canonical.amount,
                direction=canonical.direction,
                merchant_name=canonical.merchant_name,
                normalized_merchant=canonical.normalized_merchant,
                source_name=self._dominant_value([item.source_name for item in members]),
                category=category,
                confidence=max(item.classification_confidence for item in members),
                reason="Manual merge undo preserved original transaction."
                if group_key.startswith("manual:")
                else ("Grouped duplicate transactions." if duplicate_count else canonical.classification_reason),
                duplicate_count=duplicate_count,
                is_active=True,
            )
            self.session.add(merged)
            self.session.flush()
            for member in members:
                if group_key.startswith("manual:"):
                    member.merge_status = MergeStatus.UNDONE
                elif duplicate_count:
                    member.merge_status = MergeStatus.MERGED
                else:
                    member.merge_status = MergeStatus.UNMERGED
                self.session.add(
                    MergedTransactionMember(
                        merged_transaction_id=merged.id,
                        normalized_transaction_id=member.id,
                    )
                )

    def _parse_table(self, content: bytes) -> list[dict[str, str]]:
        decoded = content.decode("utf-8-sig")
        sample = decoded[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)
        return [dict(row) for row in reader]

    def _normalize_row(self, row: dict[str, str], import_source_name: str) -> dict:
        occurred_on = self._parse_date(self._extract_value(row, "occurred_on"))
        amount = self._parse_amount(self._extract_value(row, "amount"))
        direction = self._parse_direction(self._extract_value(row, "direction"), amount)
        merchant_name = str(self._extract_value(row, "merchant_name") or "Unknown Merchant").strip()
        normalized_merchant = self._normalize_merchant_name(merchant_name)
        source_name = str(self._extract_value(row, "source_name") or import_source_name).strip()
        external_id = str(self._extract_value(row, "external_id") or "").strip()
        note = str(self._extract_value(row, "note") or "").strip()
        card_last4 = str(self._extract_value(row, "card_last4") or "").strip()
        normalized = {
            "occurred_on": occurred_on,
            "amount": abs(amount),
            "direction": direction,
            "merchant_name": merchant_name,
            "normalized_merchant": normalized_merchant,
            "source_name": source_name,
            "channel": import_source_name,
            "external_id": external_id,
            "note": note,
            "card_last4": card_last4[-4:],
            "dedupe_key": self._dedupe_key(occurred_on, amount, direction, normalized_merchant, external_id),
        }
        classification = self._classify_transaction(normalized)
        normalized.update(
            {
                "category_suggested": classification.category,
                "category_final": classification.category,
                "classification_confidence": classification.confidence,
                "classification_reason": classification.reason,
                "classifier_name": classification.classifier_name,
            }
        )
        return normalized

    def _apply_classification(self, transaction: NormalizedTransaction) -> None:
        classification = self._classify_transaction(
            {
                "merchant_name": transaction.merchant_name,
                "note": transaction.note,
                "direction": transaction.direction,
                "amount": transaction.amount,
                "source_name": transaction.source_name,
            }
        )
        transaction.category_suggested = classification.category
        transaction.category_final = classification.category
        transaction.classification_confidence = classification.confidence
        transaction.classification_reason = classification.reason
        transaction.classifier_name = classification.classifier_name

    def _classify_transaction(self, payload: dict):
        start = time.perf_counter()
        serializable_payload = self._serialize_for_json(payload)
        try:
            result = self.classifier.classify(payload)
            latency_ms = int((time.perf_counter() - start) * 1000)
            self.session.add(
                ModelCallLog(
                    classifier_name=result.classifier_name,
                    request_payload=serializable_payload,
                    response_payload={
                        "category": result.category,
                        "confidence": result.confidence,
                        "reason": result.reason,
                    },
                    latency_ms=latency_ms,
                    success=True,
                )
            )
            return result
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            self.session.add(
                ModelCallLog(
                    classifier_name=getattr(self.classifier, "__class__.__name__", "unknown"),
                    request_payload=serializable_payload,
                    success=False,
                    error_message=str(exc),
                    latency_ms=latency_ms,
                )
            )
            fallback = RuleBasedClassifier()
            result = fallback.classify(payload)
            result.reason = f"{result.reason} Fallback used after classifier error: {exc}"
            return result

    def _serialize_for_json(self, value):
        if isinstance(value, dict):
            return {k: self._serialize_for_json(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._serialize_for_json(v) for v in value]
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        return value

    def _extract_value(self, row: dict[str, str], field_name: str):
        normalized_row = {self._normalize_header(key): value for key, value in row.items()}
        for alias in self.FIELD_ALIASES[field_name]:
            alias_value = normalized_row.get(self._normalize_header(alias))
            if alias_value not in (None, ""):
                return alias_value
        return ""

    def _normalize_header(self, value: str) -> str:
        return re.sub(r"[^a-z0-9\u4e00-\u9fa5]+", "", value.lower())

    def _parse_date(self, value: str) -> date:
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Unsupported date format: {value}")

    def _parse_amount(self, value: str) -> Decimal:
        text = str(value).strip()
        # Handle accounting notation (100.00) -> -100.00
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
        sanitized = re.sub(r"[^\d\-.]", "", text)
        if not sanitized:
            raise ValueError(f"Unsupported amount: {value}")
        try:
            return Decimal(sanitized)
        except InvalidOperation as exc:
            raise ValueError(f"Unsupported amount: {value}") from exc

    def _parse_direction(self, value: str, amount: Decimal) -> BillDirection:
        text = str(value).strip().lower()
        if text in {"income", "in", "credit", "收入"}:
            return BillDirection.INCOME
        if text in {"expense", "out", "debit", "支出"}:
            return BillDirection.EXPENSE
        return BillDirection.INCOME if amount < 0 else BillDirection.EXPENSE

    def _normalize_merchant_name(self, merchant_name: str) -> str:
        text = merchant_name.lower()
        text = re.sub(r"(limited|inc|co\.|ltd|company)", "", text)
        text = re.sub(r"[^a-z0-9\u4e00-\u9fa5]+", "", text)
        return text or "unknownmerchant"

    def _dedupe_key(
        self,
        occurred_on: date,
        amount: Decimal,
        direction: BillDirection,
        normalized_merchant: str,
        external_id: str,
    ) -> str:
        if external_id:
            return f"{direction.value}:{external_id}"
        return f"{direction.value}:{occurred_on.isoformat()}:{abs(amount):.2f}:{normalized_merchant}"

    def _dominant_category(self, members: list[NormalizedTransaction]) -> str:
        categories = [member.category_final or member.category_suggested or "other" for member in members]
        return self._dominant_value(categories)

    def _dominant_value(self, values: list[str]) -> str:
        counts = Counter(value for value in values if value)
        if not counts:
            return "unknown"
        return counts.most_common(1)[0][0]

    def _account_key(self, transaction: MergedTransaction) -> str:
        accounts = [
            member.normalized_transaction.card_last4
            for member in transaction.members
            if member.normalized_transaction.card_last4
        ]
        if accounts:
            return f"card:{self._dominant_value(accounts)}"
        return f"source:{transaction.source_name}"

    def _record_audit(self, action: str, entity_type: str, entity_id: str, details: dict) -> None:
        self.session.add(
            AuditLog(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details,
            )
        )
