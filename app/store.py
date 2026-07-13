from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app import clock as clock_mod
from app import idgen
from app.config import Settings
from app.constants import TYPE_CLIENT_DETAILS
from app.kafka_publisher import KafkaPublisher, NullPublisher, Publisher
from app.models import ClientView, Event, RegisterRequest, RegisterResponse
from app.redis_live import RedisLive

LOG = logging.getLogger("trustedge-agent-api")


@dataclass
class DeviceRecord:
    device_id: str
    device_token: str = ""
    last_details: dict[str, Any] = field(default_factory=dict)
    last_seen_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "device_id": self.device_id,
            "device_token": self.device_token,
        }
        if self.last_details:
            out["last_details"] = self.last_details
        if self.last_seen_at is not None:
            out["last_seen_at"] = self.last_seen_at.isoformat().replace("+00:00", "Z")
        return out


class EventStore:
    def __init__(
        self,
        settings: Settings,
        *,
        redis_live: RedisLive | None = None,
        publisher: Publisher | None = None,
    ) -> None:
        self._settings = settings
        self._max_events = settings.max_events if settings.max_events > 0 else 500
        self._disable_disk = not settings.persist_files()
        self._data_dir = Path(settings.data_dir)
        self._lock = threading.RLock()
        self._devices: dict[str, DeviceRecord] = {}
        self._tokens: dict[str, str] = {}
        self._events: dict[str, list[Event]] = {}
        self._redis = redis_live
        self._publisher = publisher or NullPublisher()

        if not self._disable_disk:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._load_disk()
        if self._redis is not None and self._disable_disk:
            self._load_from_redis()

    @classmethod
    def from_settings(cls, settings: Settings) -> EventStore:
        redis_live: RedisLive | None = None
        if settings.redis_url.strip():
            redis_live = RedisLive(settings.redis_url.strip(), settings.max_events)
        publisher: Publisher = NullPublisher()
        if settings.kafka_brokers.strip():
            publisher = KafkaPublisher(settings.kafka_brokers.strip(), settings.kafka_topic)
        return cls(settings, redis_live=redis_live, publisher=publisher)

    @property
    def redis_enabled(self) -> bool:
        return self._redis is not None

    @property
    def kafka_enabled(self) -> bool:
        return not isinstance(self._publisher, NullPublisher)

    def close(self) -> None:
        if self._redis is not None:
            self._redis.close()
        self._publisher.close()

    def _load_disk(self) -> None:
        devices_path = self._data_dir / "devices.json"
        if devices_path.exists():
            data = json.loads(devices_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    rec = self._record_from_dict(item)
                    if rec.device_id:
                        self._devices[rec.device_id] = rec
                        if rec.device_token:
                            self._tokens[rec.device_token] = rec.device_id

        events_path = self._data_dir / "events.jsonl"
        if events_path.exists():
            for line in events_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    event = Event.model_validate(payload)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not event.device_id:
                    continue
                events = self._events.setdefault(event.device_id, [])
                events.append(event)
                if len(events) > self._max_events:
                    self._events[event.device_id] = events[-self._max_events :]

    def _load_from_redis(self) -> None:
        if self._redis is None:
            return
        for item in self._redis.load_device_auth():
            rec = self._record_from_dict(item)
            if not rec.device_id:
                continue
            self._devices[rec.device_id] = rec
            if rec.device_token:
                self._tokens[rec.device_token] = rec.device_id

    @staticmethod
    def _record_from_dict(data: dict[str, Any]) -> DeviceRecord:
        last_seen = data.get("last_seen_at")
        parsed_seen: datetime | None = None
        if isinstance(last_seen, str) and last_seen:
            text = last_seen[:-1] + "+00:00" if last_seen.endswith("Z") else last_seen
            try:
                parsed_seen = datetime.fromisoformat(text)
            except ValueError:
                parsed_seen = None
        details = data.get("last_details")
        return DeviceRecord(
            device_id=str(data.get("device_id") or ""),
            device_token=str(data.get("device_token") or ""),
            last_details=details if isinstance(details, dict) else {},
            last_seen_at=parsed_seen,
        )

    def _persist_devices(self) -> None:
        if self._disable_disk:
            return
        records = [rec.to_dict() for rec in self._devices.values()]
        path = self._data_dir / "devices.json"
        path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)

    def _append_event(self, event: Event) -> None:
        if self._disable_disk:
            return
        path = self._data_dir / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json", by_alias=False)) + "\n")
        os.chmod(path, 0o600)

    def register(self, req: RegisterRequest) -> RegisterResponse:
        with self._lock:
            device_id = req.device_id or idgen.new_device_id()
            rec = self._devices.get(device_id)
            if rec is None:
                rec = DeviceRecord(device_id=device_id)
                self._devices[device_id] = rec
            if not rec.device_token:
                rec.device_token = idgen.new_token()
                self._tokens[rec.device_token] = device_id

            now = clock_mod.now_utc()
            rec.last_seen_at = now
            if req.hostname:
                rec.last_details["hostname"] = req.hostname
            if req.os:
                rec.last_details["os"] = req.os
            if req.os_version:
                rec.last_details["os_version"] = req.os_version
            if req.arch:
                rec.last_details["arch"] = req.arch
            if req.agent_version:
                rec.last_details["agent_version"] = req.agent_version

            self._persist_devices()
            if self._redis is not None:
                self._redis.upsert_register(device_id, rec.last_details, now)
                if self._disable_disk:
                    self._redis.save_device_auth(rec.to_dict())

            return RegisterResponse(device_id=device_id, device_token=rec.device_token)

    def device_id_for_token(self, token: str) -> str | None:
        with self._lock:
            return self._tokens.get(token)

    def add_event(self, event: Event) -> None:
        with self._lock:
            rec = self._devices.get(event.device_id)
            if rec is None:
                rec = DeviceRecord(device_id=event.device_id)
                self._devices[event.device_id] = rec

            ts = event.ts or clock_mod.now_utc()
            event.ts = ts
            rec.last_seen_at = ts
            if event.type == TYPE_CLIENT_DETAILS:
                rec.last_details = dict(event.payload)

            events = self._events.setdefault(event.device_id, [])
            events.append(event)
            if len(events) > self._max_events:
                events = events[-self._max_events :]
            self._events[event.device_id] = events

            self._append_event(event)
            self._persist_devices()
            if self._redis is not None:
                self._redis.upsert_event(event)
                if self._disable_disk:
                    self._redis.save_device_auth(rec.to_dict())
            self._publisher.publish_event(event)

    def get_client(self, device_id: str, limit: int = 50) -> ClientView | None:
        with self._lock:
            rec = self._devices.get(device_id)
            if rec is None:
                return None
            if limit <= 0:
                limit = 50
            events = list(self._events.get(device_id, []))
            if len(events) > limit:
                events = events[-limit:]
            return ClientView(
                device_id=rec.device_id,
                last_details=rec.last_details or None,
                last_seen_at=rec.last_seen_at,
                recent_events=events,
            )
