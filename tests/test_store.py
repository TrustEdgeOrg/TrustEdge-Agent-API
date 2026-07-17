from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings
from app.core.constants import TYPE_CLIENT_DETAILS, TYPE_PROCESS_START
from app.models.schemas import Event, RegisterRequest
from app.store.event_store import EventStore


class MockPublisher:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def publish_event(self, event: Event) -> None:
        self.events.append(event)

    def close(self) -> None:
        return None


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


def test_add_events_writes_devices_once(tmp_path, monkeypatch) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"), production=False)
    store = EventStore.from_settings(settings)
    reg = store.register(RegisterRequest(hostname="batch-host"))
    saves = {"n": 0}
    original = store._disk.save_devices

    def counting_save(devices):
        saves["n"] += 1
        return original(devices)

    monkeypatch.setattr(store._disk, "save_devices", counting_save)
    batch = [
        Event(
            event_id=f"evt_{i}",
            device_id=reg.device_id,
            type=TYPE_PROCESS_START,
            payload={"pid": i},
        )
        for i in range(8)
    ]
    store.add_events(batch)
    assert saves["n"] == 1
    assert len(store.get_client(reg.device_id, limit=20).recent_events) == 8
    store.close()
