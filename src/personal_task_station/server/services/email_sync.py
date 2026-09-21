"""Email account seeding and sync orchestration shared by API routes and the
background poller thread."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from personal_task_station.server.importers.email.client import ImapConfig
from personal_task_station.server.importers.email.service import EmailImportService
from personal_task_station.shared.models import BillImportJob, EmailAccount, EmailImportLog, utcnow
from personal_task_station.shared.settings import AppSettings

logger = logging.getLogger(__name__)


def build_imap_config(account: EmailAccount) -> ImapConfig:
    return ImapConfig(
        host=account.imap_host,
        port=account.imap_port,
        username=account.username,
        password=account.password,
        folder=account.folder,
        use_ssl=account.use_ssl,
    )


def seed_env_email_account(session: Session, settings: AppSettings) -> EmailAccount | None:
    """Create/refresh the default EmailAccount from ``PTS_IMAP_*`` env vars.

    Idempotent: matches on (host, username); refreshes the stored password when
    it changed so rotating an IMAP auth code only requires the env var.
    Returns ``None`` when no mailbox is configured in the environment.
    """
    if not settings.imap_host or not settings.imap_username or not settings.imap_password:
        return None

    account = (
        session.query(EmailAccount)
        .filter(EmailAccount.imap_host == settings.imap_host)
        .filter(EmailAccount.username == settings.imap_username)
        .one_or_none()
    )
    if account is None:
        account = EmailAccount(
            name=f"imap:{settings.imap_username}",
            imap_host=settings.imap_host,
            imap_port=settings.imap_port,
            username=settings.imap_username,
            password=settings.imap_password,
            folder=settings.imap_folder,
            use_ssl=settings.imap_use_ssl,
        )
        session.add(account)
        logger.info("Seeded default email account %s from environment", settings.imap_username)
    else:
        if not account.is_active:
            account.is_active = True
        if account.password != settings.imap_password:
            account.password = settings.imap_password
        account.port = account.imap_port or settings.imap_port
    session.commit()
    session.refresh(account)
    return account


def run_account_import(
    session: Session,
    account: EmailAccount,
    since_date: date | None = None,
    ignore_seen: bool = False,
    mark_seen: bool = True,
):
    """Fetch one mailbox and push parsed transactions through the ledger.

    Ingestion goes through :class:`IngestService.deliver_transactions` so that
    replayed/duplicated emails are idempotent by their transaction ids. Returns
    the created ``BillImportJob`` or ``None`` when everything was a duplicate.
    """
    config = build_imap_config(account)
    try:
        service = EmailImportService(config)
        results = service.import_from_email(
            since_date=since_date, mark_seen=mark_seen, ignore_seen=ignore_seen
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as failed route/log entry
        raise RuntimeError(f"IMAP sync failed for {account.username}: {exc}") from exc

    from personal_task_station.server.services.ingest import IngestService

    ingest = IngestService(session)
    raw_txs = [tx for result in results for tx in result.raw_transactions]
    report = ingest.deliver_transactions(
        raw_txs,
        source_name=f"email:{account.name}",
        filename="email_import",
    )

    import_job = None
    if report.import_job_id is not None:
        import_job = session.get(BillImportJob, report.import_job_id)

    account.last_import_at = utcnow()
    for result in results:
        session.add(
            EmailImportLog(
                email_account_id=account.id,
                email_uid="batch",
                email_subject=result.email_subject[:500],
                email_from=result.email_from[:255],
                parser_used=result.source_name,
                transaction_count=len(result.raw_transactions),
                error_message="; ".join(result.errors)[:1000],
            )
        )
    session.commit()
    if import_job is not None:
        session.refresh(import_job)
    return import_job


def sync_accounts(
    session: Session,
    *,
    since_date: date | None = None,
    throttle_minutes: int = 60,
    force: bool = False,
    ignore_seen: bool = False,
) -> list:
    """Sync every active email account, respecting a per-account throttle."""
    accounts = (
        session.query(EmailAccount)
        .filter(EmailAccount.is_active == True)  # noqa: E712
        .all()
    )

    jobs = []
    for account in accounts:
        if not force and account.last_import_at:
            age_minutes = (
                datetime.now(timezone.utc)
                - account.last_import_at.replace(tzinfo=timezone.utc)
            ).total_seconds() / 60
            if age_minutes < throttle_minutes:
                continue
        try:
            job = run_account_import(
                session, account, since_date=since_date, ignore_seen=ignore_seen
            )
        except Exception as exc:  # noqa: BLE001 - keep syncing other accounts
            logger.warning("Email sync failed for account %s: %s", account.id, exc)
            continue
        if job is not None:
            jobs.append(job)
    return jobs
