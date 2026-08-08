"""Fail-open writer for TrustEdge live twin keys in Redis.

Key contract (shared with TrustEdge backend trusttwin_store):
  twin:devices                  SET of device_id
  twin:device:{id}:latest       JSON DeviceLatest
  twin:device:{id}:events       ZSET of event envelopes (score = unix ms)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.constants import (
    TYPE_ACTION_SUMMARY,
    TYPE_CLIENT_DETAILS,
    TYPE_KNOWN_AI_APP,
    TYPE_NETWORK_SUMMARY,
)
from app.models.schemas import Event

LOG = logging.getLogger("trustedge-agent-api.twin")

DEVICES_KEY = "twin:devices"
LATEST_KEY_FMT = "twin:device:{device_id}:latest"
EVENTS_KEY_FMT = "twin:device:{device_id}:events"
EVENTS_CAP = 200


def _ts_iso(value: Optional[datetime]) -> str:
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _score_ms(value: Optional[datetime]) -> int:
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


class TwinRedisStore:
    """Best-effort Redis twin updater. Never raises to callers."""

    def __init__(self, redis_url: str) -> None:
        self._url = (redis_url or "").strip()
        self._client: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self._url)

    def _get_client(self) -> Any | None:
        if not self._url:
            return None
        if self._client is not None:
            return self._client
        try:
            import redis

            self._client = redis.Redis.from_url(self._url, decode_responses=True)
            self._client.ping()
            return self._client
        except Exception as exc:  # noqa: BLE001 — fail-open
            LOG.warning("twin redis unavailable: %s", exc)
            self._client = None
            return None

    def apply_events(self, device_id: str, events: list[Event]) -> None:
        if not device_id or not events:
            return
        client = self._get_client()
        if client is None:
            return
        try:
            latest_key = LATEST_KEY_FMT.format(device_id=device_id)
            events_key = EVENTS_KEY_FMT.format(device_id=device_id)

            raw_latest = client.get(latest_key)
            doc: dict[str, Any] = {
                "device_id": device_id,
                "last_seen_at": None,
                "client_details": {},
                "network_summary": {},
                "action_summary": {},
                "known_ai_apps": {},
            }
            if raw_latest:
                try:
                    parsed = json.loads(raw_latest)
                    if isinstance(parsed, dict):
                        doc.update(parsed)
                        doc["device_id"] = device_id
                        for field in (
                            "client_details",
                            "network_summary",
                            "action_summary",
                            "known_ai_apps",
                        ):
                            if not isinstance(doc.get(field), dict):
                                doc[field] = {}
                except json.JSONDecodeError:
                    pass

            pipe = client.pipeline()
            pipe.sadd(DEVICES_KEY, device_id)

            for event in events:
                ts = event.ts
                doc["last_seen_at"] = _ts_iso(ts)
                payload = event.payload if isinstance(event.payload, dict) else {}
                if event.type == TYPE_CLIENT_DETAILS:
                    doc["client_details"] = dict(payload)
                elif event.type == TYPE_NETWORK_SUMMARY:
                    doc["network_summary"] = dict(payload)
                elif event.type == TYPE_ACTION_SUMMARY:
                    doc["action_summary"] = dict(payload)
                elif event.type == TYPE_KNOWN_AI_APP:
                    apps = doc["known_ai_apps"]
                    if not isinstance(apps, dict):
                        apps = {}
                        doc["known_ai_apps"] = apps
                    app_id = str(payload.get("id") or "").strip()
                    if app_id:
                        if payload.get("removed") is True:
                            apps.pop(app_id, None)
                        else:
                            apps[app_id] = dict(payload)

                envelope = {
                    "event_id": event.event_id or "",
                    "device_id": device_id,
                    "type": event.type,
                    "ts": _ts_iso(ts),
                    "payload": payload,
                }
                pipe.zadd(events_key, {json.dumps(envelope, separators=(",", ":")): _score_ms(ts)})

            pipe.set(latest_key, json.dumps(doc, separators=(",", ":")))
            # Keep newest EVENTS_CAP members.
            pipe.zremrangebyrank(events_key, 0, -(EVENTS_CAP + 1))
            pipe.execute()
        except Exception as exc:  # noqa: BLE001 — fail-open
            LOG.warning("twin redis update failed for device_id=%s: %s", device_id, exc)
            self._client = None


def twin_store_from_url(redis_url: str) -> TwinRedisStore:
    return TwinRedisStore(redis_url)
