from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from .settings import AppSettings


def require_api_key(request: Request) -> None:
    settings = AppSettings.load()
    received = request.headers.get("X-API-Key", "")
    expected = settings.api_key
    if not hmac.compare_digest(received, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
        )
