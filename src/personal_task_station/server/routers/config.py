from __future__ import annotations

from fastapi import APIRouter, Depends

from personal_task_station.shared.schemas import ConnectionConfig
from personal_task_station.shared.settings import AppSettings

router = APIRouter(prefix="/config", tags=["config"])


def _mask_key(key: str) -> str:
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


@router.get("/client-defaults", response_model=ConnectionConfig)
def client_defaults(settings: AppSettings = Depends(AppSettings.load)) -> ConnectionConfig:
    scheme = "https" if settings.ssl_certfile else "http"
    return ConnectionConfig(
        base_url=f"{scheme}://{settings.host}:{settings.port}",
        api_key=_mask_key(settings.api_key),
        verify_tls=True,
        server_cert_path=settings.server_cert_path,
        client_cert_path=settings.client_cert_path,
        client_key_path=settings.client_key_path,
        allow_insecure_localhost=False,
        timeout_seconds=settings.request_timeout_seconds,
    )
