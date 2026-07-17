from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Union

from fastapi import APIRouter, Depends, Request
from starlette.responses import PlainTextResponse, Response

from app.api.errors import plain_error
from app.api.ingest import decode_events, read_request_body
from app.clients.trustedge_backend import upsert_agent_fields
from app.config import Settings, get_settings
from app.core import clock as clock_mod
from app.core.auth import bearer_token
from app.core.constants import (
    ALLOWED_EVENT_TYPES,
    ERR_BAD_REQUEST,
    ERR_BATCH_TOO_LARGE,
    ERR_DEVICE_ID_MISMATCH,
    ERR_INTERNAL,
    ERR_INVALID_JSON,
    ERR_UNAUTHORIZED,
    ERR_UNKNOWN_EVENT_TYPE,
    MAX_EVENTS_PER_BATCH,
    STATUS_ACCEPTED,
)
from app.dependencies import get_store
from app.models.schemas import Event
from app.store.event_store import EventStore

router = APIRouter()
LOG = logging.getLogger("trustedge-agent-api")


def _persist_and_details(
    store: EventStore, device_id: str, events: list[Event]
) -> tuple[int, dict[str, Any]]:
    store.add_events(events)
    details: dict[str, Any] = {}
    client = store.get_client(device_id, limit=1)
    if client and client.last_details:
        details = dict(client.last_details)
    return len(events), details


def _schedule_upsert(settings: Settings, device_id: str, details: dict[str, Any]) -> None:
    """Run TrustEdge upsert off the event loop; never delay the 202 response."""

    async def _run() -> None:
        await asyncio.to_thread(
            upsert_agent_fields,
            settings,
            device_id,
            hostname=str(details["hostname"]) if details.get("hostname") else None,
            os=str(details["os"]) if details.get("os") else None,
            os_version=str(details["os_version"]) if details.get("os_version") else None,
            arch=str(details["arch"]) if details.get("arch") else None,
            agent_version=str(details["agent_version"]) if details.get("agent_version") else None,
            status="active",
        )

    task = asyncio.create_task(_run())

    def _done(done: asyncio.Task[None]) -> None:
        try:
            done.result()
        except Exception as exc:  # noqa: BLE001 — fail-open background upsert
            LOG.warning("background agent upsert failed for device_id=%s: %s", device_id, exc)

    task.add_done_callback(_done)


@router.post("/events", response_model=None)
async def ingest_events(
    request: Request,
    store: EventStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> Union[Response, PlainTextResponse]:
    token = bearer_token(request)
    if not token:
        return plain_error(ERR_UNAUTHORIZED, 401)
    device_id = store.device_id_for_token(token)
    if not device_id:
        return plain_error(ERR_UNAUTHORIZED, 401)

    try:
        body = await read_request_body(request)
        events = decode_events(body)
    except ValueError as exc:
        msg = str(exc) or ERR_BAD_REQUEST
        if msg == ERR_INVALID_JSON:
            return plain_error(ERR_INVALID_JSON, 400)
        return plain_error(ERR_BAD_REQUEST, 400)

    if not events:
        return plain_error(ERR_BAD_REQUEST, 400)
    if len(events) > MAX_EVENTS_PER_BATCH:
        return plain_error(ERR_BATCH_TOO_LARGE, 400)

    for event in events:
        if not event.device_id:
            event.device_id = device_id
        if event.device_id != device_id:
            return plain_error(ERR_DEVICE_ID_MISMATCH, 403)
        if event.type not in ALLOWED_EVENT_TYPES:
            return plain_error(ERR_UNKNOWN_EVENT_TYPE, 400)
        if event.ts is None:
            event.ts = clock_mod.now_utc()
        if not event.event_id:
            event.event_id = clock_mod.new_event_id(event.ts)

    try:
        accepted, details = await asyncio.to_thread(_persist_and_details, store, device_id, events)
    except OSError:
        return plain_error(ERR_INTERNAL, 500)

    # Ensure agent appears in TrustEdge Postgres even when the client skipped
    # /v1/register (stored credentials). Fail-open if backend is unset/down.
    _schedule_upsert(settings, device_id, details)

    return Response(
        content=json.dumps({"status": STATUS_ACCEPTED, "accepted": accepted}),
        status_code=202,
        media_type="application/json",
    )
