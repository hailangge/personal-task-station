from __future__ import annotations

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


def main() -> None:
    settings = AppSettings.load()
    uvicorn.run(
        "personal_task_station.server.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
