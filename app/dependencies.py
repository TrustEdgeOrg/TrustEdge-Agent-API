from __future__ import annotations

from fastapi import Request

from app.config import Settings, get_settings
from app.store.event_store import EventStore


def get_store(request: Request) -> EventStore:
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise RuntimeError("store not initialized")
    return store


__all__ = ["Settings", "get_settings", "get_store", "EventStore"]
