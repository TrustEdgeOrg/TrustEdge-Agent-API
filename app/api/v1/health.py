from __future__ import annotations

from fastapi import APIRouter

from app.core.constants import STATUS_OK

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": STATUS_OK}
