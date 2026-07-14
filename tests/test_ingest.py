from __future__ import annotations

import zstandard as zstd

from app.api.ingest import decode_events
from app.core.codec import decompress, is_zstd
from app.core.constants import TYPE_CLIENT_DETAILS, TYPE_PROCESS_START
from app.models.schemas import Event, EventBatch


def test_decode_events_single() -> None:
    events = decode_events(b'{"type":"client_details","payload":{"hostname":"x"}}')
    assert len(events) == 1
    assert events[0].type == TYPE_CLIENT_DETAILS


def test_decode_events_batch() -> None:
    body = b'{"events":[{"type":"process_start","payload":{"pid":1}},{"type":"process_exit","payload":{"pid":1}}]}'
    events = decode_events(body)
    assert len(events) == 2


def test_decode_events_batch_model() -> None:
    raw = EventBatch(events=[Event(type=TYPE_PROCESS_START)]).model_dump_json().encode()
    events = decode_events(raw)
    assert len(events) == 1


def test_read_request_body_zstd() -> None:
    plain = EventBatch(events=[Event(type=TYPE_PROCESS_START, payload={"pid": 1})]).model_dump_json().encode()
    compressed = zstd.ZstdCompressor().compress(plain)
    assert is_zstd("zstd")
    body = decompress(compressed)
    events = decode_events(body)
    assert len(events) == 1
