from __future__ import annotations

import json
from typing import Union

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
from app.store.event_store import EventStore

router = APIRouter()


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

    accepted = 0
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
            store.add_event(event)
        except OSError:
            return plain_error(ERR_INTERNAL, 500)
        accepted += 1

    # Ensure agent appears in TrustEdge Postgres even when the client skipped
    # /v1/register (stored credentials). Fail-open if backend is unset/down.
    details: dict = {}
    client = store.get_client(device_id, limit=1)
    if client and client.last_details:
        details = client.last_details
    upsert_agent_fields(
        settings,
        device_id,
        hostname=str(details["hostname"]) if details.get("hostname") else None,
        os=str(details["os"]) if details.get("os") else None,
        os_version=str(details["os_version"]) if details.get("os_version") else None,
        arch=str(details["arch"]) if details.get("arch") else None,
        agent_version=str(details["agent_version"]) if details.get("agent_version") else None,
        status="active",
    )

    return Response(
        content=json.dumps({"status": STATUS_ACCEPTED, "accepted": accepted}),
        status_code=202,
        media_type="application/json",
    )
