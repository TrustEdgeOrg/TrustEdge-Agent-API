from __future__ import annotations

import threading
from datetime import timedelta
from pathlib import Path
from typing import Optional

from app.config import Settings
from app.core import clock as clock_mod
from app.core import idgen
from app.core.constants import TYPE_CLIENT_DETAILS
from app.core.tokens import hash_device_token
from app.models.schemas import ClientView, Event, RegisterRequest, RegisterResponse
from app.publishers.base import Publisher
from app.publishers.kafka import NullPublisher, publisher_from_settings
from app.store.device_creds import DeviceCredsBackend, device_creds_from_settings
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
        creds: Optional[DeviceCredsBackend] = None,
    ) -> None:
        self._settings = settings
        self._pepper = (settings.device_token_pepper or "").strip()
        self._ttl_sec = max(0, int(settings.device_token_ttl_sec or 0))
        self._max_events = settings.max_events if settings.max_events > 0 else 500
        self._disk = DiskPersistence(Path(settings.data_dir), enabled=settings.persist_files())
        self._lock = threading.RLock()
        self._devices: dict[str, DeviceRecord] = {}
        self._events: dict[str, list[Event]] = {}
        self._publisher = publisher or NullPublisher()
        self._twin = twin if twin is not None else twin_store_from_url(settings.redis_url)
        self._creds = creds if creds is not None else device_creds_from_settings(settings)
        self._load_from_disk()
        self._hydrate_creds_from_local_if_needed()

    @classmethod
    def from_settings(cls, settings: Settings) -> EventStore:
        publisher = publisher_from_settings(settings.kafka_brokers, settings.kafka_topic)
        return cls(settings, publisher=publisher, twin=twin_store_from_url(settings.redis_url))

    @property
    def kafka_enabled(self) -> bool:
        return not isinstance(self._publisher, NullPublisher)

    @property
    def shared_creds_enabled(self) -> bool:
        return bool((self._settings.device_creds_database_url or "").strip())

    @property
    def device_creds_cache_enabled(self) -> bool:
        if not self.shared_creds_enabled:
            return False
        from app.store.device_creds import CachedDeviceCreds

        return isinstance(self._creds, CachedDeviceCreds)

    def close(self) -> None:
        self._publisher.close()
        self._creds.close()

    def _hash(self, token: str) -> str:
        return hash_device_token(token, pepper=self._pepper)

    def _expiry_from_now(self):
        if self._ttl_sec <= 0:
            return None
        return clock_mod.now_utc() + timedelta(seconds=self._ttl_sec)

    def _load_from_disk(self) -> None:
        dirty = False
        for rec in self._disk.load_devices():
            if not rec.device_id:
                continue
            before = (rec.device_token, rec.device_token_hash)
            rec.ensure_token_hash(pepper=self._pepper)
            if (rec.device_token, rec.device_token_hash) != before:
                dirty = True
            self._devices[rec.device_id] = rec
        self._events = self._disk.load_events(self._max_events)
        if dirty:
            self._disk.save_devices(self._devices)

    def _hydrate_creds_from_local_if_needed(self) -> None:
        """Seed shared/memory creds from local device records (migration / single-node)."""
        for rec in self._devices.values():
            if not rec.device_token_hash or rec.revoked_at is not None:
                continue
            existing = self._creds.get(rec.device_id)
            if existing and existing.token_hash:
                continue
            self._creds.upsert_active(
                rec.device_id,
                token_hash=rec.device_token_hash,
                token_expires_at=rec.token_expires_at,
                last_seen_at=rec.last_seen_at,
            )

    def _issue_token(self, rec: DeviceRecord) -> str:
        """Mint a new opaque token, store only its hash, return plaintext once."""
        plaintext = idgen.new_token()
        digest = self._hash(plaintext)
        expires = self._expiry_from_now()
        now = clock_mod.now_utc()
        rec.device_token = ""
        rec.device_token_hash = digest
        rec.token_expires_at = expires
        rec.revoked_at = None
        self._creds.upsert_active(
            rec.device_id,
            token_hash=digest,
            token_expires_at=expires,
            last_seen_at=now,
        )
        return plaintext

    def register(self, req: RegisterRequest) -> RegisterResponse:
        """Register or re-register a device.

        Re-registration always rotates the device token so the API can return a
        usable plaintext secret without storing plaintext at rest.
        """
        with self._lock:
            device_id = req.device_id or idgen.new_device_id()
            rec = self._devices.get(device_id)
            if rec is None:
                rec = DeviceRecord(device_id=device_id)
                self._devices[device_id] = rec

            plaintext = self._issue_token(rec)

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
            return RegisterResponse(device_id=device_id, device_token=plaintext)

    def rotate_token(self, current_token: str) -> RegisterResponse | None:
        """Rotate credentials for the device authenticated by current_token."""
        with self._lock:
            device_id = self._lookup_device_id_locked(current_token)
            if not device_id:
                return None
            rec = self._devices.get(device_id)
            if rec is None:
                rec = DeviceRecord(device_id=device_id)
                self._devices[device_id] = rec
            plaintext = self._issue_token(rec)
            rec.last_seen_at = clock_mod.now_utc()
            self._disk.save_devices(self._devices)
            return RegisterResponse(device_id=device_id, device_token=plaintext)

    def revoke_device(self, device_id: str) -> bool:
        """Revoke device credentials. Returns False if device unknown."""
        with self._lock:
            device_id = device_id.strip()
            now = clock_mod.now_utc()
            revoked = self._creds.revoke(device_id, revoked_at=now)
            rec = self._devices.get(device_id)
            if rec is not None:
                rec.device_token = ""
                rec.device_token_hash = ""
                rec.token_expires_at = None
                rec.revoked_at = now
                self._disk.save_devices(self._devices)
                return True
            return revoked

    def _lookup_device_id_locked(self, token: str) -> str | None:
        digest = self._hash(token)
        if not digest:
            return None
        return self._creds.lookup_active_device_id(digest)

    def device_id_for_token(self, token: str) -> str | None:
        with self._lock:
            return self._lookup_device_id_locked(token)

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
                try:
                    self._creds.touch_last_seen(event.device_id, last_seen_at=ts)
                except Exception:  # noqa: BLE001 — fail-open for local event path
                    pass
            self._disk.save_devices(self._devices)
        for event in to_publish:
            self._publisher.publish_event(event)
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
