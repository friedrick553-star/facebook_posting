"""FastAPI dependency — instant 503 when DB startup is not finished yet."""
from __future__ import annotations

from fastapi import HTTPException, Request, status


def require_db_ready(request: Request) -> None:
    if getattr(request.app.state, "db_ready", False):
        return
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database still connecting — wait a few seconds and try again.",
    )
