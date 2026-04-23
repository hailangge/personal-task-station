from __future__ import annotations

from fastapi import APIRouter, Depends

from personal_task_station.shared.schemas import ConnectionConfig
from personal_task_station.shared.settings import AppSettings

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/client-defaults", response_model=ConnectionConfig)
def client_defaults(settings: AppSettings = Depends(AppSettings.load)) -> ConnectionConfig:
    return ConnectionConfig(
        base_url=f"http://{settings.host}:{settings.port}",
        api_key=settings.api_key,
        verify_tls=True,
        server_cert_path=settings.server_cert_path,
        client_cert_path=settings.client_cert_path,
        client_key_path=settings.client_key_path,
        allow_insecure_localhost=settings.allow_insecure_localhost,
        timeout_seconds=settings.request_timeout_seconds,
    )
