"""Ingestion service: webhook deliveries (bank SMS) and screenshot drafts."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from personal_task_station.server.importers.base import RawTransaction
from personal_task_station.server.importers.sms import parse_bank_sms
from personal_task_station.server.services.billing import BillingService
from personal_task_station.shared.enums import BillDirection
from personal_task_station.shared.models import NormalizedTransaction, ScreenshotIngestDraft
from personal_task_station.shared.schemas import ScreenshotConfirmRequest
from personal_task_station.shared.settings import AppSettings


@dataclass(slots=True)
class DeliveryReport:
    status: str  # created | skipped_duplicate | ignored
    transaction_count: int = 0
    duplicate_count: int = 0
    import_job_id: int | None = None
    message: str = ""
    errors: list[str] = field(default_factory=list)


class IngestService:
    def __init__(self, session: Session, settings: AppSettings | None = None):
        self.session = session
        self.settings = settings or AppSettings.load()

    # ------------------------------------------------------------------ SMS
    def deliver_sms_text(self, text: str, source_name: str = "sms_webhook") -> DeliveryReport:
        raw_tx = parse_bank_sms(text, source_name=source_name)
        if raw_tx is None:
            return DeliveryReport(status="ignored", message="no dynamic-account signal found")
        return self.deliver_transactions([raw_tx], source_name=source_name, filename="webhook_sms")

    # ------------------------------------------------------- shared pipeline
    def deliver_transactions(
        self,
        raw_txs: list[RawTransaction],
        *,
        source_name: str,
        filename: str,
    ) -> DeliveryReport:
        """Idempotently push parsed transactions through the billing pipeline.

        Transactions carrying an external_id that already exists in the ledger
        are counted as duplicates and skipped.
        """
        if not raw_txs:
            return DeliveryReport(status="ignored", message="no transactions provided")

        incoming_ids = [tx.external_id for tx in raw_txs if tx.external_id]
        duplicates: set[str] = set()
        if incoming_ids:
            rows = self.session.execute(
                select(NormalizedTransaction.external_id).where(
                    NormalizedTransaction.external_id.in_(incoming_ids)
                )
            ).all()
            duplicates = {row[0] for row in rows}

        pending = [tx for tx in raw_txs if not tx.external_id or tx.external_id not in duplicates]
        if not pending:
            return DeliveryReport(
                status="skipped_duplicate",
                duplicate_count=len(duplicates),
                message=f"all {len(duplicates)} transaction(s) already ingested",
            )

        billing = BillingService(session=self.session)
        import_job = billing.create_import_job(source_name=source_name, filename=filename)
        for tx in pending:
            billing.add_raw_transaction_from_email(import_job.id, tx)
        # Sessions are configured with autoflush=False; normalize_transactions
        # counts rows via SQL queries, so make the inserts visible first.
        self.session.flush()
        billing.normalize_transactions(import_job.id)
        billing.merge_and_classify(import_job.id)
        self.session.commit()
        self.session.refresh(import_job)

        return DeliveryReport(
            status="created",
            transaction_count=len(pending),
            duplicate_count=len(duplicates),
            import_job_id=import_job.id,
        )

    # ------------------------------------------------------------ screenshots
    def create_screenshot_draft(self, image_bytes: bytes, filename: str) -> ScreenshotIngestDraft:
        """Store the image and produce a confirm-first draft.

        Uses the LiteLLM vision extractor when configured; otherwise the draft
        is still created (empty proposal + error note) so the user can fill in
        fields manually via ``confirm_draft``.
        """
        digest = hashlib.sha256(image_bytes).hexdigest()
        existing = (
            self.session.query(ScreenshotIngestDraft)
            .filter(ScreenshotIngestDraft.sha256 == digest)
            .first()
        )
        if existing is not None:
            return existing

        storage_dir = Path(os.environ.get("PTS_DATA_DIR", ".local/pts-data")) / "screenshots"
        storage_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix.lower() or ".png"
        stored_path = storage_dir / f"{digest[:16]}{suffix}"
        stored_path.write_bytes(image_bytes)

        errors: list[str] = []
        proposed: dict = {}
        try:
            from personal_task_station.server.services.vision_extract import (
                VisionExtractionError,
                extract_transaction_from_image,
            )

            mime = "image/png" if suffix in ("", ".png") else "image/jpeg"
            proposal = extract_transaction_from_image(image_bytes, mime_type=mime, settings=self.settings)
            proposed = dict(proposal)
        except VisionExtractionError as exc:
            errors.append(str(exc))

        draft = ScreenshotIngestDraft(
            filename=filename[:255],
            stored_path=str(stored_path),
            sha256=digest,
            status="proposed",
            proposed_payload=proposed,
            extraction_errors=errors,
        )
        self.session.add(draft)
        self.session.commit()
        self.session.refresh(draft)
        return draft

    def confirm_draft(self, draft_id: int, request: ScreenshotConfirmRequest) -> ScreenshotIngestDraft:
        """Turn an approved draft into a ledger transaction (idempotent)."""
        draft = self.session.get(ScreenshotIngestDraft, draft_id)
        if not draft:
            raise ValueError(f"Draft {draft_id} not found")
        if draft.status != "proposed":
            raise ValueError(f"Draft {draft_id} is already {draft.status}")

        payload = dict(draft.proposed_payload or {})
        occurred_raw = str(request.occurred_on.isoformat() if request.occurred_on else payload.get("occurred_on", ""))
        amount_value = request.amount if request.amount is not None else payload.get("amount", "")
        direction = request.direction
        if direction is None:
            direction_raw = str(payload.get("direction", "expense"))
            direction = BillDirection.INCOME if str(direction_raw).startswith(("in", "收")) else BillDirection.EXPENSE
        merchant = (
            request.merchant_name
            if request.merchant_name is not None
            else str(payload.get("merchant_name", ""))
        )

        if not occurred_raw or not amount_value:
            raise ValueError("Missing required fields: occurred_on and amount")

        raw_tx = RawTransaction(
            source_name="screenshot",
            occurred_on=date.fromisoformat(occurred_raw[:10]),
            amount=abs(Decimal(str(amount_value))),
            direction=direction,
            merchant_name=(merchant.strip() or "截图交易"),
            channel=request.channel or "screenshot",
            card_last4="",
            note=request.note or str(payload.get("note", "")),
            external_id=f"screenshot:{draft.sha256[:24]}",
            raw_data={"draft_id": draft.id, "stored_path": draft.stored_path},
        )
        report = self.deliver_transactions(
            [raw_tx], source_name="screenshot", filename=draft.filename or "screenshot.png"
        )
        if report.status != "created":
            draft.status = "discarded"
            draft.extraction_errors = list(draft.extraction_errors or []) + [report.message]
        else:
            draft.status = "confirmed"
            confirmed_id = self.session.execute(
                select(NormalizedTransaction.id)
                .where(NormalizedTransaction.import_job_id == report.import_job_id)
                .limit(1)
            ).scalar()
            draft.confirmed_transaction_id = confirmed_id
        draft.proposed_payload = {
            **payload,
            "occurred_on": str(raw_tx.occurred_on),
            "amount": str(raw_tx.amount),
            "direction": "income" if raw_tx.direction == BillDirection.INCOME else "expense",
            "merchant_name": raw_tx.merchant_name,
        }
        self.session.commit()
        self.session.refresh(draft)
        return draft

    def discard_draft(self, draft_id: int, reason: str = "") -> ScreenshotIngestDraft:
        draft = self.session.get(ScreenshotIngestDraft, draft_id)
        if not draft:
            raise ValueError(f"Draft {draft_id} not found")
        if draft.status != "proposed":
            raise ValueError(f"Draft {draft_id} is already {draft.status}")
        draft.status = "discarded"
        if reason:
            draft.extraction_errors = list(draft.extraction_errors or []) + [reason]
        self.session.commit()
        self.session.refresh(draft)
        return draft

    def list_drafts(self, status_filter: str | None = None) -> list[ScreenshotIngestDraft]:
        query = self.session.query(ScreenshotIngestDraft).order_by(ScreenshotIngestDraft.id.desc())
        if status_filter:
            query = query.filter(ScreenshotIngestDraft.status == status_filter)
        return query.limit(200).all()
