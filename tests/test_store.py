from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.core.constants import TYPE_CLIENT_DETAILS, TYPE_PROCESS_START
from app.core.tokens import hash_device_token
from app.models.schemas import Event, RegisterRequest
from app.store.device_record import DeviceRecord, device_record_from_dict
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
        # Plaintext must not be persisted.
        raw = (data_dir / "devices.json").read_text(encoding="utf-8")
        assert reg.device_token not in raw
        assert "device_token_hash" in raw
    finally:
        store2.close()


def test_register_rotates_token(tmp_path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"), production=False)
    store = EventStore.from_settings(settings)
    first = store.register(RegisterRequest(device_id="dev_fixed", hostname="h1"))
    second = store.register(RegisterRequest(device_id="dev_fixed", hostname="h2"))
    assert first.device_id == second.device_id
    assert first.device_token != second.device_token
    assert store.device_id_for_token(first.device_token) is None
    assert store.device_id_for_token(second.device_token) == "dev_fixed"
    store.close()


def test_revoke_device_blocks_token(tmp_path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"), production=False)
    store = EventStore.from_settings(settings)
    reg = store.register(RegisterRequest(hostname="revoked-host"))
    assert store.revoke_device(reg.device_id) is True
    assert store.device_id_for_token(reg.device_token) is None
    store.close()


def test_rotate_token_endpoint_logic(tmp_path) -> None:
    settings = Settings(data_dir=str(tmp_path / "data"), production=False)
    store = EventStore.from_settings(settings)
    reg = store.register(RegisterRequest(hostname="rotate-host"))
    rotated = store.rotate_token(reg.device_token)
    assert rotated is not None
    assert rotated.device_id == reg.device_id
    assert rotated.device_token != reg.device_token
    assert store.device_id_for_token(reg.device_token) is None
    assert store.device_id_for_token(rotated.device_token) == reg.device_id
    store.close()


def test_token_ttl_expiry(tmp_path, monkeypatch) -> None:
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        production=False,
        device_token_ttl_sec=60,
    )
    store = EventStore.from_settings(settings)
    reg = store.register(RegisterRequest(hostname="ttl-host"))
    row = store._creds.get(reg.device_id)
    assert row is not None
    row.token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert store.device_id_for_token(reg.device_token) is None
    store.close()


def test_legacy_plaintext_migrates_to_hash(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    plaintext = "tok_legacy_plain_value_000000000000"
    legacy = DeviceRecord(device_id="dev_legacy", device_token=plaintext)
    # Simulate old on-disk shape.
    import json

    (data_dir / "devices.json").write_text(
        json.dumps(
            [
                {
                    "device_id": "dev_legacy",
                    "device_token": plaintext,
                }
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    store = EventStore.from_settings(Settings(data_dir=str(data_dir), production=False))
    try:
        assert store.device_id_for_token(plaintext) == "dev_legacy"
        raw = (data_dir / "devices.json").read_text(encoding="utf-8")
        assert plaintext not in raw
        assert hash_device_token(plaintext) in raw
    finally:
        store.close()


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


def test_device_record_roundtrip_hash_only() -> None:
    rec = device_record_from_dict(
        {
            "device_id": "dev_x",
            "device_token_hash": "abc",
            "token_expires_at": "2026-01-01T00:00:00Z",
        }
    )
    dumped = rec.to_dict()
    assert "device_token" not in dumped
    assert dumped["device_token_hash"] == "abc"
