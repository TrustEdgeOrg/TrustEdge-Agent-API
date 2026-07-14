from __future__ import annotations

from fastapi import Request

from app.core.codec import decompress, is_zstd
from app.core.constants import ERR_BAD_REQUEST, ERR_INVALID_JSON
from app.models.schemas import Event, EventBatch


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
