from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from personal_task_station.server.dependencies import get_db
from personal_task_station.server.importers.email.client import ImapConfig
from personal_task_station.server.importers.email.service import EmailImportService
from personal_task_station.server.services.billing import BillingService
from personal_task_station.shared.models import EmailAccount, EmailImportLog
from personal_task_station.shared.schemas import (
    EmailAccountCreate,
    EmailAccountRead,
    EmailAccountUpdate,
    EmailImportPreview,
    EmailImportResult,
    ImportJobRead,
)

router = APIRouter(prefix="/email-import", tags=["email-import"])


def _billing_service(session: Session) -> BillingService:
    return BillingService(session)


@router.get("/accounts", response_model=list[EmailAccountRead])
def list_accounts(session: Session = Depends(get_db)) -> list[EmailAccountRead]:
    return session.query(EmailAccount).all()


@router.post("/accounts", response_model=EmailAccountRead, status_code=status.HTTP_201_CREATED)
def create_account(payload: EmailAccountCreate, session: Session = Depends(get_db)) -> EmailAccountRead:
    account = EmailAccount(**payload.model_dump())
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@router.patch("/accounts/{account_id}", response_model=EmailAccountRead)
def update_account(account_id: int, payload: EmailAccountUpdate, session: Session = Depends(get_db)) -> EmailAccountRead:
    account = session.get(EmailAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, key, value)
    session.commit()
    session.refresh(account)
    return account


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, session: Session = Depends(get_db)) -> None:
    account = session.get(EmailAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    session.delete(account)
    session.commit()


@router.get("/accounts/{account_id}/preview", response_model=list[EmailImportPreview])
def preview_emails(account_id: int, session: Session = Depends(get_db)) -> list[EmailImportPreview]:
    account = session.get(EmailAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    config = ImapConfig(
        host=account.imap_host,
        port=account.imap_port,
        username=account.username,
        password=account.password,
        folder=account.folder,
        use_ssl=account.use_ssl,
    )
    try:
        service = EmailImportService(config)
        emails = service.preview_emails(since_date=date.today() - timedelta(days=30))
        return [
            EmailImportPreview(uid=e.uid, subject=e.subject, from_addr=e.from_addr, date=e.date)
            for e in emails
        ]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/import", response_model=ImportJobRead)
def import_from_email(
    account_id: int,
    since_date: date | None = None,
    session: Session = Depends(get_db),
) -> ImportJobRead:
    account = session.get(EmailAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if not account.is_active:
        raise HTTPException(status_code=400, detail="Account is inactive")

    config = ImapConfig(
        host=account.imap_host,
        port=account.imap_port,
        username=account.username,
        password=account.password,
        folder=account.folder,
        use_ssl=account.use_ssl,
    )

    try:
        service = EmailImportService(config)
        results = service.import_from_email(since_date=since_date, mark_seen=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Create import job and feed transactions into billing pipeline
    import_job = _billing_service(session).create_import_job(
        source_name=f"email:{account.name}",
        filename="email_import",
    )

    total_tx = 0
    for result in results:
        for tx in result.raw_transactions:
            _billing_service(session).add_raw_transaction_from_email(import_job.id, tx)
            total_tx += 1

    # Normalize and merge
    _billing_service(session).normalize_transactions(import_job.id)
    _billing_service(session).merge_and_classify(import_job.id)

    # Update account last_import
    from personal_task_station.shared.models import utcnow

    account.last_import_at = utcnow()
    session.commit()

    # Log import results
    for result in results:
        log = EmailImportLog(
            email_account_id=account.id,
            email_uid="batch",
            parser_used=result.source_name,
            transaction_count=len(result.raw_transactions),
            error_message="; ".join(result.errors) if result.errors else "",
        )
        session.add(log)
    session.commit()

    session.refresh(import_job)
    return ImportJobRead.model_validate(import_job)


@router.get("/accounts/{account_id}/logs", response_model=list[dict])
def list_import_logs(account_id: int, session: Session = Depends(get_db)) -> list[dict]:
    account = session.get(EmailAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    logs = (
        session.query(EmailImportLog)
        .filter(EmailImportLog.email_account_id == account_id)
        .order_by(EmailImportLog.imported_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": log.id,
            "parser_used": log.parser_used,
            "transaction_count": log.transaction_count,
            "error_message": log.error_message,
            "imported_at": log.imported_at.isoformat(),
        }
        for log in logs
    ]
