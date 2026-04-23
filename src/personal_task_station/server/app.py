from __future__ import annotations

import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI

from personal_task_station.server.routers import billing, config, health, tasks
from personal_task_station.shared.database import Base, get_engine
from personal_task_station.shared.security import require_api_key
from personal_task_station.shared.settings import AppSettings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=get_engine(app.state.database_url))
    yield


def create_app(database_url: str | None = None) -> FastAPI:
    settings = AppSettings.load()
    app = FastAPI(title="Personal Task Station", version="0.1.0", lifespan=lifespan)
    app.state.database_url = database_url or settings.database_url

    app.include_router(health.router)
    app.include_router(config.router, dependencies=[Depends(require_api_key)])
    app.include_router(tasks.router, dependencies=[Depends(require_api_key)])
    app.include_router(billing.router, dependencies=[Depends(require_api_key)])
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
