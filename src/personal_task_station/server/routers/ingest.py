from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from personal_task_station.server.dependencies import get_db
from personal_task_station.server.services.ingest import IngestService
from personal_task_station.shared.schemas import (
    IngestDeliveryRead,
    ScreenshotConfirmRequest,
    ScreenshotDraftRead,
    ScreenshotDiscardRequest,
)

router = APIRouter(prefix="/ingest", tags=["ingest"])

_TEXT_PAYLOAD_KEYS = ("text", "content", "message", "sms", "body", "raw")


def _service(session: Session) -> IngestService:
    return IngestService(session)


@router.post("/webhook", response_model=IngestDeliveryRead)
async def webhook_delivery(
    request: Request,
    source_name: str = Form(default="sms_webhook"),
    session: Session = Depends(get_db),
) -> IngestDeliveryRead:
    """Receive forwarded SMS / payment notifications (e.g. via SmsForwarder).

    Accepts either a JSON object containing one of the common text keys
    (``text`` / ``content`` / ``message`` / ``sms`` / ``body`` / ``raw``) or a
    plain text body. Authentication uses the standard ``X-API-Key`` header so
    existing key-management applies. Delivery is idempotent: re-sending the
    same message reports ``skipped_duplicate`` instead of double counting.
    """
    content_type = request.headers.get("content-type", "")
    text = ""
    if content_type.startswith("application/json"):
        try:
            payload = json.loads((await request.body()).decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        for key in _TEXT_PAYLOAD_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                break
        supplied_source = payload.get("source_name")
        if isinstance(supplied_source, str) and supplied_source.strip():
            source_name = supplied_source.strip()
    else:
        raw_body = (await request.body()).decode("utf-8", errors="replace")
        if content_type.startswith("application/x-www-form-urlencoded"):
            form = await request.form()
            text_value = form.get("text") or form.get("content") or ""
            text = str(text_value).strip()
            form_source = form.get("source_name")
            if isinstance(form_source, str) and form_source.strip():
                source_name = form_source.strip()
        elif raw_body.strip():
            text = raw_body.strip()

    if not text:
        return IngestDeliveryRead(
            status="ignored",
            transaction_count=0,
            duplicate_count=0,
            import_job_id=None,
            message="empty body: expected JSON with a text field or plain text",
        )

    try:
        report = _service(session).deliver_sms_text(text, source_name=source_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return IngestDeliveryRead(
        status=report.status,
        transaction_count=report.transaction_count,
        duplicate_count=report.duplicate_count,
        import_job_id=report.import_job_id,
        message=report.message,
    )


@router.post("/screenshots", response_model=ScreenshotDraftRead, status_code=status.HTTP_201_CREATED)
async def upload_screenshot(
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> ScreenshotDraftRead:
    """Upload one payment screenshot; returns a proposal awaiting confirmation."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")
    draft = _service(session).create_screenshot_draft(content, filename=file.filename or "screenshot.png")
    return ScreenshotDraftRead.model_validate(draft)


@router.get("/screenshots", response_model=list[ScreenshotDraftRead])
def list_screenshots(
    status_filter: str | None = None,
    session: Session = Depends(get_db),
) -> list[ScreenshotDraftRead]:
    return [
        ScreenshotDraftRead.model_validate(draft)
        for draft in _service(session).list_drafts(status_filter)
    ]


@router.post("/screenshots/{draft_id}/confirm", response_model=ScreenshotDraftRead)
def confirm_screenshot(
    draft_id: int,
    payload: ScreenshotConfirmRequest,
    session: Session = Depends(get_db),
) -> ScreenshotDraftRead:
    try:
        draft = _service(session).confirm_draft(draft_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScreenshotDraftRead.model_validate(draft)


@router.delete("/screenshots/{draft_id}", response_model=ScreenshotDraftRead)
def discard_screenshot(
    draft_id: int,
    payload: ScreenshotDiscardRequest | None = None,
    session: Session = Depends(get_db),
) -> ScreenshotDraftRead:
    reason = payload.reason if payload else ""
    try:
        draft = _service(session).discard_draft(draft_id, reason)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 400, detail=str(exc)) from exc
    return ScreenshotDraftRead.model_validate(draft)
