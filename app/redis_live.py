from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import redis

from app import clock as clock_mod
from app.constants import (
    REDIS_DEVICE_TOKENS_KEY,
    REDIS_DEVICES_KEY,
    REDIS_EVENTS_KEY_FMT,
    REDIS_LATEST_KEY_FMT,
    TYPE_ACTION_SUMMARY,
    TYPE_CLIENT_DETAILS,
    TYPE_NETWORK_SUMMARY,
)
from app.models import Event

LOG = logging.getLogger("trustedge-agent-api")


class DeviceLatest:
    def __init__(
        self,
        device_id: str,
        last_seen_at: datetime | None = None,
        client_details: dict[str, Any] | None = None,
        network_summary: dict[str, Any] | None = None,
        action_summary: dict[str, Any] | None = None,
    ) -> None:
        self.device_id = device_id
        self.last_seen_at = last_seen_at
        self.client_details = client_details or {}
        self.network_summary = network_summary or {}
        self.action_summary = action_summary or {}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"device_id": self.device_id}
        if self.last_seen_at is not None:
            out["last_seen_at"] = self.last_seen_at.isoformat().replace("+00:00", "Z")
        if self.client_details:
            out["client_details"] = self.client_details
        if self.network_summary:
            out["network_summary"] = self.network_summary
        if self.action_summary:
            out["action_summary"] = self.action_summary
        return out


def _latest_key(device_id: str) -> str:
    return REDIS_LATEST_KEY_FMT.format(device_id=device_id)


def _events_key(device_id: str) -> str:
    return REDIS_EVENTS_KEY_FMT.format(device_id=device_id)


def _device_auth_key(device_id: str) -> str:
    return f"twin:device:{device_id}:auth"


class RedisLive:
    def __init__(self, redis_url: str, max_events: int) -> None:
        self._client = redis.from_url(redis_url, decode_responses=False)
        self._client.ping()
        self._max_events = max_events

    def close(self) -> None:
        self._client.close()

    def save_device_auth(self, record: dict[str, Any]) -> None:
        device_id = str(record.get("device_id") or "")
        if not device_id:
            return
        pipe = self._client.pipeline()
        pipe.set(_device_auth_key(device_id), json.dumps(record))
        token = str(record.get("device_token") or "")
        if token:
            pipe.hset(REDIS_DEVICE_TOKENS_KEY, token, device_id)
        pipe.execute()

    def load_device_auth(self) -> list[dict[str, Any]]:
        token_map = self._client.hgetall(REDIS_DEVICE_TOKENS_KEY)
        seen: set[str] = set()
        records: list[dict[str, Any]] = []
        for device_id_raw in token_map.values():
            device_id = device_id_raw.decode() if isinstance(device_id_raw, bytes) else str(device_id_raw)
            if not device_id or device_id in seen:
                continue
            seen.add(device_id)
            raw = self._client.get(_device_auth_key(device_id))
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                records.append(data)
        return records

    def _load_latest(self, device_id: str) -> DeviceLatest:
        raw = self._client.get(_latest_key(device_id))
        if not raw:
            return DeviceLatest(device_id=device_id)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return DeviceLatest(device_id=device_id)
        if not isinstance(data, dict):
            return DeviceLatest(device_id=device_id)
        last_seen = data.get("last_seen_at")
        parsed_seen: datetime | None = None
        if isinstance(last_seen, str) and last_seen:
            text = last_seen[:-1] + "+00:00" if last_seen.endswith("Z") else last_seen
            try:
                parsed_seen = datetime.fromisoformat(text)
            except ValueError:
                parsed_seen = None
        return DeviceLatest(
            device_id=device_id,
            last_seen_at=parsed_seen,
            client_details=data.get("client_details") if isinstance(data.get("client_details"), dict) else {},
            network_summary=data.get("network_summary") if isinstance(data.get("network_summary"), dict) else {},
            action_summary=data.get("action_summary") if isinstance(data.get("action_summary"), dict) else {},
        )

    def _save_latest(self, doc: DeviceLatest) -> None:
        pipe = self._client.pipeline()
        pipe.sadd(REDIS_DEVICES_KEY, doc.device_id)
        pipe.set(_latest_key(doc.device_id), json.dumps(doc.to_dict()))
        pipe.execute()

    def upsert_register(self, device_id: str, details: dict[str, Any], seen_at: datetime) -> None:
        doc = self._load_latest(device_id)
        doc.last_seen_at = seen_at
        for key, value in details.items():
            if value is None:
                continue
            if isinstance(value, str) and value == "":
                continue
            doc.client_details[key] = value
        try:
            self._save_latest(doc)
        except redis.RedisError as exc:
            LOG.warning("redis register %s: %s", device_id, exc)

    def upsert_event(self, event: Event) -> None:
        doc = self._load_latest(event.device_id)
        ts = event.ts or clock_mod.now_utc()
        doc.last_seen_at = ts
        if event.type == TYPE_CLIENT_DETAILS:
            doc.client_details = dict(event.payload)
        elif event.type == TYPE_NETWORK_SUMMARY:
            doc.network_summary = dict(event.payload)
        elif event.type == TYPE_ACTION_SUMMARY:
            doc.action_summary = dict(event.payload)

        ev_data = json.dumps(event.model_dump(mode="json", by_alias=False))
        score = ts.timestamp() * 1000.0
        pipe = self._client.pipeline()
        pipe.sadd(REDIS_DEVICES_KEY, event.device_id)
        pipe.set(_latest_key(event.device_id), json.dumps(doc.to_dict()))
        pipe.zadd(_events_key(event.device_id), {ev_data: score})
        if self._max_events > 0:
            pipe.zremrangebyrank(_events_key(event.device_id), 0, -(self._max_events + 1))
        try:
            pipe.execute()
        except redis.RedisError as exc:
            LOG.warning("redis event %s: %s", event.device_id, exc)
