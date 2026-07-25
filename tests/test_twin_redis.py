from __future__ import annotations

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
