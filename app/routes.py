from __future__ import annotations

import json
from typing import Union

from fastapi import APIRouter, Depends, Request
from starlette.responses import PlainTextResponse, Response

from app import clock as clock_mod
from app.auth import bearer_token
from app.codec import decompress, is_zstd
from app.config import Settings, get_settings
from app.constants import (
    ALLOWED_EVENT_TYPES,
    ERR_BAD_REQUEST,
    ERR_BATCH_TOO_LARGE,
    ERR_DEVICE_ID_MISMATCH,
    ERR_INTERNAL,
    ERR_INVALID_JSON,
    ERR_NOT_FOUND,
    ERR_UNAUTHORIZED,
    ERR_UNKNOWN_EVENT_TYPE,
    MAX_EVENTS_PER_BATCH,
    STATUS_ACCEPTED,
    STATUS_OK,
)
from app.models import Event, EventBatch, RegisterRequest, RegisterResponse
from app.store import EventStore

router = APIRouter()
_store: EventStore | None = None


def set_store(store: EventStore) -> None:
    global _store
    _store = store


def get_store() -> EventStore:
    if _store is None:
        raise RuntimeError("store not initialized")
    return _store


def plain_error(message: str, status_code: int) -> PlainTextResponse:
    return PlainTextResponse(content=message, status_code=status_code)


def decode_events(body: bytes) -> list[Event]:
    try:
        batch = EventBatch.model_validate_json(body)
        if batch.events:
            return batch.events
    except ValueError:
        pass
    try:
        single = Event.model_validate_json(body)
    except ValueError as exc:
        raise ValueError(ERR_INVALID_JSON) from exc
    if not single.type:
        raise ValueError(ERR_INVALID_JSON)
    return [single]


async def read_request_body(request: Request) -> bytes:
    raw = await request.body()
    if len(raw) > 1 << 20:
        raise ValueError(ERR_BAD_REQUEST)
    if not is_zstd(request.headers.get("Content-Encoding")):
        return raw
    return decompress(raw)


@router.get("/healthz")
def healthz() -> dict:
    return {"status": STATUS_OK}


@router.post("/v1/register", response_model=None)
async def register(
    request: Request,
    settings: Settings = Depends(get_settings),
    store: EventStore = Depends(get_store),
) -> Union[RegisterResponse, PlainTextResponse]:
    if settings.enroll_token and bearer_token(request) != settings.enroll_token:
        return plain_error(ERR_UNAUTHORIZED, 401)

    body = await request.body()
    if len(body) > 1 << 20:
        return plain_error(ERR_BAD_REQUEST, 400)
    req = RegisterRequest()
    if body:
        try:
            req = RegisterRequest.model_validate_json(body)
        except ValueError:
            return plain_error(ERR_INVALID_JSON, 400)

    try:
        resp = store.register(req)
    except OSError:
        return plain_error(ERR_INTERNAL, 500)
    return resp


@router.post("/v1/events", response_model=None)
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
    except ValueError:
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


@router.get("/v1/clients/{device_id}", response_model=None)
def get_client(device_id: str, store: EventStore = Depends(get_store)) -> Union[Response, PlainTextResponse]:
    view = store.get_client(device_id, 50)
    if view is None:
        return plain_error(ERR_NOT_FOUND, 404)
    return Response(
        content=json.dumps(view.model_dump(mode="json", by_alias=False)),
        status_code=200,
        media_type="application/json",
    )
