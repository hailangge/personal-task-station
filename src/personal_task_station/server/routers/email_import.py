from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from personal_task_station.server.dependencies import get_db
from personal_task_station.server.importers.email.client import ImapConfig
from personal_task_station.server.importers.email.service import EmailImportService
from personal_task_station.server.services.email_sync import run_account_import, sync_accounts
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
def preview_emails(
    account_id: int,
    since_date: date | None = None,
    ignore_seen: bool = False,
    session: Session = Depends(get_db),
) -> list[EmailImportPreview]:
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
        since = since_date or (date.today() - timedelta(days=30))
        emails = service.preview_emails(since_date=since, ignore_seen=ignore_seen)
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
    ignore_seen: bool = False,
    session: Session = Depends(get_db),
) -> ImportJobRead:
    account = session.get(EmailAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if not account.is_active:
        raise HTTPException(status_code=400, detail="Account is inactive")

    try:
        import_job = run_account_import(session, account, since_date=since_date, ignore_seen=ignore_seen)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - IMAP/network errors surface as 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if import_job is None:
        raise HTTPException(
            status_code=409,
            detail="No new transactions ingested (all duplicates or nothing parsed)",
        )

    session.refresh(import_job)
    return ImportJobRead.model_validate(import_job)


@router.post("/sync", response_model=list[ImportJobRead])
def sync_all_accounts(
    since_date: date | None = None,
    force: bool = False,
    session: Session = Depends(get_db),
) -> list[ImportJobRead]:
    """Sync all active email accounts for new transactions.

    Skips accounts whose last import was within the past hour unless
    ``force=true`` is passed; the background poller passes ``force`` every run.
    """
    jobs = sync_accounts(session, since_date=since_date, force=force)
    return [ImportJobRead.model_validate(job) for job in jobs]


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
