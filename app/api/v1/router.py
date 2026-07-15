from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import clients, events, health, register

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(register.router, prefix="/v1", tags=["register"])
router.include_router(events.router, prefix="/v1", tags=["events"])
router.include_router(clients.router, prefix="/v1", tags=["clients"])
