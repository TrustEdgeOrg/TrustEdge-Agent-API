from __future__ import annotations

import json
from typing import Union

from fastapi import APIRouter, Depends, Request
from starlette.responses import PlainTextResponse, Response

from app.api.errors import plain_error
from app.api.ingest import decode_events, read_request_body
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

    return Response(
        content=json.dumps({"status": STATUS_ACCEPTED, "accepted": accepted}),
        status_code=202,
        media_type="application/json",
    )
