from __future__ import annotations

from datetime import datetime, timezone

import pytest
import zstandard as zstd
from fastapi.testclient import TestClient

from app.codec import decompress, is_zstd
from app.config import Settings
from app.constants import TYPE_ACTION_SUMMARY, TYPE_CLIENT_DETAILS, TYPE_PROCESS_START
from app.main import create_app
from app.models import Event, EventBatch, RegisterRequest
from app.routes import decode_events
from app.store import EventStore


class MockPublisher:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def publish_event(self, event: Event) -> None:
        self.events.append(event)

    def close(self) -> None:
        return None


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


def test_disable_disk_persistence_skips_json_files(tmp_path) -> None:
    data_dir = tmp_path / "data"
    settings = Settings(
        data_dir=str(data_dir),
        production=False,
        persist_files_override="0",
    )
    store = EventStore.from_settings(settings)
    reg = store.register(RegisterRequest(hostname="test-host"))
    store.add_event(
        Event(
            event_id="evt_1",
            device_id=reg.device_id,
            type=TYPE_CLIENT_DETAILS,
            payload={"hostname": "test-host"},
        )
    )
    assert not (data_dir / "devices.json").exists()
    assert not (data_dir / "events.jsonl").exists()
    store.close()


def test_disk_persistence_restores_auth(tmp_path) -> None:
    data_dir = tmp_path / "data"
    settings = Settings(data_dir=str(data_dir), production=False)
    store1 = EventStore.from_settings(settings)
    reg = store1.register(RegisterRequest(hostname="persist-me"))
    store1.close()

    store2 = EventStore.from_settings(Settings(data_dir=str(data_dir), production=False))
    try:
        device_id = store2.device_id_for_token(reg.device_token)
        assert device_id == reg.device_id
    finally:
        store2.close()


def test_add_event_publishes_to_kafka(tmp_path) -> None:
    publisher = MockPublisher()
    settings = Settings(data_dir=str(tmp_path / "data"), production=False)
    store = EventStore(settings, publisher=publisher)
    reg = store.register(RegisterRequest(hostname="test-host"))
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    event = Event(
        event_id="evt_kafka",
        device_id=reg.device_id,
        type=TYPE_CLIENT_DETAILS,
        ts=now,
        payload={"hostname": "test-host"},
    )
    store.add_event(event)
    assert len(publisher.events) == 1
    assert publisher.events[0].event_id == "evt_kafka"
    store.close()


@pytest.fixture
def api_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("TRUSTEDGE_AGENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TRUSTEDGE_AGENT_PRODUCTION", "0")
    with TestClient(create_app()) as client:
        yield client


def test_healthz(api_client: TestClient) -> None:
    resp = api_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_register_and_events_flow(api_client: TestClient) -> None:
    reg = api_client.post("/v1/register", json={"hostname": "mbp", "os": "darwin"})
    assert reg.status_code == 200
    token = reg.json()["device_token"]
    device_id = reg.json()["device_id"]

    events = api_client.post(
        "/v1/events",
        headers={"Authorization": f"Bearer {token}"},
        json={"events": [{"type": "client_details", "payload": {"hostname": "mbp", "status": "online"}}]},
    )
    assert events.status_code == 202
    assert events.json()["accepted"] == 1

    client_view = api_client.get(f"/v1/clients/{device_id}")
    assert client_view.status_code == 200
    assert client_view.json()["device_id"] == device_id
