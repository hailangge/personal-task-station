from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from personal_task_station.server.dependencies import get_db
from personal_task_station.server.services.billing import BillingService
from personal_task_station.shared.schemas import (
    ImportJobRead,
    MergedTransactionRead,
    ModelCallLogRead,
    MonthlySummary,
    NormalizedTransactionRead,
    ReanalyzeRequest,
)

router = APIRouter(prefix="/billing", tags=["billing"])


def _service(session: Session) -> BillingService:
    return BillingService(session)


@router.post("/import", response_model=ImportJobRead, status_code=status.HTTP_201_CREATED)
async def import_billing_file(
    source_name: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> ImportJobRead:
    try:
        content = await file.read()
        return _service(session).import_csv_bytes(source_name=source_name, filename=file.filename or "import.csv", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/imports", response_model=list[ImportJobRead])
def list_import_jobs(session: Session = Depends(get_db)) -> list[ImportJobRead]:
    return _service(session).list_import_jobs()


@router.post("/reanalyze")
def reanalyze(payload: ReanalyzeRequest, session: Session = Depends(get_db)) -> dict[str, str]:
    _service(session).reanalyze(payload.import_job_id)
    return {"status": "ok"}


@router.get("/summary/monthly", response_model=MonthlySummary)
def monthly_summary(year: int, month: int, session: Session = Depends(get_db)) -> MonthlySummary:
    return _service(session).monthly_summary(year, month)


@router.get("/transactions", response_model=list[NormalizedTransactionRead])
def list_transactions(
    month: str | None = None,
    source_name: str | None = None,
    category: str | None = None,
    card_last4: str | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    session: Session = Depends(get_db),
) -> list[NormalizedTransactionRead]:
    return _service(session).list_transactions(
        month=month,
        source_name=source_name,
        category=category,
        card_last4=card_last4,
        amount_min=amount_min,
        amount_max=amount_max,
    )


@router.get("/duplicates", response_model=list[MergedTransactionRead])
def list_duplicates(session: Session = Depends(get_db)) -> list[MergedTransactionRead]:
    return _service(session).list_duplicates()


@router.post("/merged/{merged_transaction_id}/undo")
def undo_merge(merged_transaction_id: int, session: Session = Depends(get_db)) -> dict[str, str]:
    try:
        _service(session).undo_merge(merged_transaction_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "ok"}


@router.get("/model-calls", response_model=list[ModelCallLogRead])
def list_model_calls(limit: int = 100, session: Session = Depends(get_db)) -> list[ModelCallLogRead]:
    return _service(session).list_model_calls(limit=limit)
