from __future__ import annotations

import logging
import ssl
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI

from personal_task_station.server.routers import billing, config, email_import, health, ingest, tasks
from personal_task_station.shared.database import Base, get_engine, session_scope
from personal_task_station.shared.security import require_api_key
from personal_task_station.shared.settings import AppSettings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=get_engine(app.state.database_url))
    settings = getattr(app.state, "settings", None) or AppSettings.load()

    # Seed the default monitored mailbox from PTS_IMAP_* environment variables.
    try:
        from personal_task_station.server.services.email_sync import seed_env_email_account

        with session_scope(app.state.database_url) as session:
            seed_env_email_account(session, settings)
    except Exception:  # noqa: BLE001 - mailbox seeding must never block startup
        logger.warning("Failed to seed default email account", exc_info=True)

    poller_stop = threading.Event()
    app.state.email_poller_stop = poller_stop
    poller_thread = _start_email_poller(app, settings)
    try:
        yield
    finally:
        poller_stop.set()
        if poller_thread is not None:
            poller_thread.join(timeout=5)


def _start_email_poller(app: FastAPI, settings: AppSettings):
    """Run the bill-mailbox sync loop in a daemon thread when enabled.

    Enabled by setting ``PTS_EMAIL_POLL_SECONDS`` to a positive value together
    with ``PTS_IMAP_*`` credentials. Each cycle forces a full sync of all
    active accounts regardless of the per-account one-hour API throttle.
    """
    interval = max(getattr(settings, "email_poll_seconds", 0), 0)
    if interval <= 0 or not getattr(settings, "imap_host", ""):
        return None

    from personal_task_station.server.services.email_sync import sync_accounts

    stop_event = app.state.email_poller_stop

    def poll_loop() -> None:
        while not stop_event.wait(interval):
            try:
                with session_scope(app.state.database_url) as session:
                    jobs = sync_accounts(session, force=True)
                    if jobs:
                        logger.info("Email poller ingested %d job(s)", len(jobs))
            except Exception:  # noqa: BLE001 - keep polling after transient errors
                logger.warning("Email poll cycle failed", exc_info=True)

    thread = threading.Thread(target=poll_loop, name="pts-email-poller", daemon=True)
    thread.start()
    logger.info("Email poller started (interval=%ds, host=%s)", interval, settings.imap_host)
    return thread


def create_app(database_url: str | None = None) -> FastAPI:
    settings = AppSettings.load()
    app = FastAPI(title="Personal Task Station", version="0.1.0", lifespan=lifespan)
    app.state.database_url = database_url or settings.database_url
    app.state.settings = settings

    app.include_router(health.router)
    app.include_router(config.router, dependencies=[Depends(require_api_key)])
    app.include_router(tasks.router, dependencies=[Depends(require_api_key)])
    app.include_router(billing.router, dependencies=[Depends(require_api_key)])
    app.include_router(email_import.router, dependencies=[Depends(require_api_key)])
    app.include_router(ingest.router, dependencies=[Depends(require_api_key)])
    return app


app = create_app()


def _build_ssl_context(settings: AppSettings) -> ssl.SSLContext | None:
    if not settings.ssl_certfile or not settings.ssl_keyfile:
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=settings.ssl_certfile, keyfile=settings.ssl_keyfile)
    if settings.ssl_cafile:
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cafile=settings.ssl_cafile)
    return ctx


def main() -> None:
    settings = AppSettings.load()
    ssl_ctx = _build_ssl_context(settings)
    uvicorn.run(
        "personal_task_station.server.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        ssl_keyfile=settings.ssl_keyfile if ssl_ctx else None,
        ssl_certfile=settings.ssl_certfile if ssl_ctx else None,
        ssl_ca_certs=settings.ssl_cafile if ssl_ctx and settings.ssl_cafile else None,
        ssl_cert_reqs=ssl.CERT_REQUIRED if ssl_ctx and settings.ssl_cafile else ssl.CERT_NONE,
    )
