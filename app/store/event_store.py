from __future__ import annotations

import threading
from pathlib import Path

from app.config import Settings
from app.core import clock as clock_mod
from app.core import idgen
from app.core.constants import TYPE_CLIENT_DETAILS
from app.models.schemas import ClientView, Event, RegisterRequest, RegisterResponse
from app.publishers.base import Publisher
from app.publishers.kafka import NullPublisher, publisher_from_settings
from app.store.device_record import DeviceRecord
from app.store.disk import DiskPersistence
from app.store.twin_redis import TwinRedisStore, twin_store_from_url


class EventStore:
    def __init__(
        self,
        settings: Settings,
        *,
        publisher: Publisher | None = None,
        twin: TwinRedisStore | None = None,
    ) -> None:
        self._max_events = settings.max_events if settings.max_events > 0 else 500
        self._disk = DiskPersistence(Path(settings.data_dir), enabled=settings.persist_files())
        self._lock = threading.RLock()
        self._devices: dict[str, DeviceRecord] = {}
        self._tokens: dict[str, str] = {}
        self._events: dict[str, list[Event]] = {}
        self._publisher = publisher or NullPublisher()
        self._twin = twin if twin is not None else twin_store_from_url(settings.redis_url)
        self._load_from_disk()

    @classmethod
    def from_settings(cls, settings: Settings) -> EventStore:
        publisher = publisher_from_settings(settings.kafka_brokers, settings.kafka_topic)
        return cls(settings, publisher=publisher, twin=twin_store_from_url(settings.redis_url))

    @property
    def kafka_enabled(self) -> bool:
        return not isinstance(self._publisher, NullPublisher)

    def close(self) -> None:
        self._publisher.close()

    def _load_from_disk(self) -> None:
        for rec in self._disk.load_devices():
            if not rec.device_id:
                continue
            self._devices[rec.device_id] = rec
            if rec.device_token:
                self._tokens[rec.device_token] = rec.device_id
        self._events = self._disk.load_events(self._max_events)

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

            self._disk.save_devices(self._devices)
            return RegisterResponse(device_id=device_id, device_token=rec.device_token)

    def device_id_for_token(self, token: str) -> str | None:
        with self._lock:
            return self._tokens.get(token)

    def add_event(self, event: Event) -> None:
        self.add_events([event])

    def add_events(self, events: list[Event]) -> None:
        """Persist a batch under one lock and one devices.json rewrite."""
        if not events:
            return
        to_publish: list[Event] = []
        with self._lock:
            for event in events:
                rec = self._devices.get(event.device_id)
                if rec is None:
                    rec = DeviceRecord(device_id=event.device_id)
                    self._devices[event.device_id] = rec

                ts = event.ts or clock_mod.now_utc()
                event.ts = ts
                rec.last_seen_at = ts
                if event.type == TYPE_CLIENT_DETAILS:
                    rec.last_details = dict(event.payload)

                device_events = self._events.setdefault(event.device_id, [])
                device_events.append(event)
                if len(device_events) > self._max_events:
                    device_events = device_events[-self._max_events :]
                self._events[event.device_id] = device_events

                self._disk.append_event(event)
                to_publish.append(event)
            # One devices.json write per batch (was once per event — hung ingest under load).
            self._disk.save_devices(self._devices)
        for event in to_publish:
            self._publisher.publish_event(event)
        # Fail-open Redis twin update (dashboard live state / timeline).
        by_device: dict[str, list[Event]] = {}
        for event in to_publish:
            by_device.setdefault(event.device_id, []).append(event)
        for device_id, device_events in by_device.items():
            self._twin.apply_events(device_id, device_events)

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
