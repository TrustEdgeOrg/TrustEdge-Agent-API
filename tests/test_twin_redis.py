from __future__ import annotations

import json
from datetime import datetime, timezone

import fakeredis

from app.models.schemas import Event
from app.store.twin_redis import TwinRedisStore


def test_apply_events_writes_latest_and_timeline(monkeypatch):
    client = fakeredis.FakeRedis(decode_responses=True)
    store = TwinRedisStore("redis://localhost:6379/0")
    monkeypatch.setattr(store, "_get_client", lambda: client)

    ts = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    store.apply_events(
        "dev_x",
        [
            Event(
                event_id="e1",
                device_id="dev_x",
                type="client_details",
                ts=ts,
                payload={"hostname": "mbp", "os": "darwin"},
            ),
            Event(
                event_id="e2",
                device_id="dev_x",
                type="network_summary",
                ts=ts,
                payload={"public_ip": "1.2.3.4", "network_type": "wifi"},
            ),
        ],
    )

    assert "dev_x" in client.smembers("twin:devices")
    latest = client.get("twin:device:dev_x:latest")
    assert latest is not None
    assert "mbp" in latest
    assert "1.2.3.4" in latest
    events = client.zrevrange("twin:device:dev_x:events", 0, -1)
    assert len(events) == 2


def test_apply_events_folds_known_ai_apps(monkeypatch):
    client = fakeredis.FakeRedis(decode_responses=True)
    store = TwinRedisStore("redis://localhost:6379/0")
    monkeypatch.setattr(store, "_get_client", lambda: client)

    ts = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    cursor_id = "cursor:/applications/cursor.app"
    store.apply_events(
        "dev_ai",
        [
            Event(
                event_id="a1",
                device_id="dev_ai",
                type="known_ai_app",
                ts=ts,
                payload={
                    "id": cursor_id,
                    "product_id": "cursor",
                    "product_name": "Cursor",
                    "vendor": "Cursor",
                    "installed": True,
                    "running": False,
                    "version": "1.2.3",
                },
            ),
            Event(
                event_id="a2",
                device_id="dev_ai",
                type="known_ai_app",
                ts=ts,
                payload={
                    "id": "claude:/applications/claude.app",
                    "product_id": "claude",
                    "product_name": "Claude",
                    "vendor": "Anthropic",
                    "installed": True,
                    "running": True,
                },
            ),
        ],
    )

    doc = json.loads(client.get("twin:device:dev_ai:latest"))
    apps = doc["known_ai_apps"]
    assert set(apps) == {cursor_id, "claude:/applications/claude.app"}
    assert apps[cursor_id]["product_name"] == "Cursor"
    assert apps[cursor_id]["running"] is False

    store.apply_events(
        "dev_ai",
        [
            Event(
                event_id="a3",
                device_id="dev_ai",
                type="known_ai_app",
                ts=ts,
                payload={
                    "id": cursor_id,
                    "product_id": "cursor",
                    "product_name": "Cursor",
                    "installed": True,
                    "running": True,
                    "version": "1.2.4",
                },
            ),
            Event(
                event_id="a4",
                device_id="dev_ai",
                type="known_ai_app",
                ts=ts,
                payload={
                    "id": "claude:/applications/claude.app",
                    "removed": True,
                    "installed": False,
                    "running": False,
                },
            ),
        ],
    )

    doc = json.loads(client.get("twin:device:dev_ai:latest"))
    apps = doc["known_ai_apps"]
    assert set(apps) == {cursor_id}
    assert apps[cursor_id]["running"] is True
    assert apps[cursor_id]["version"] == "1.2.4"
