from __future__ import annotations

import json
import os
from pathlib import Path

from app.models.schemas import Event
from app.store.device_record import DeviceRecord, device_record_from_dict


class DiskPersistence:
    def __init__(self, data_dir: Path, *, enabled: bool) -> None:
        self._data_dir = data_dir
        self._enabled = enabled
        if self._enabled:
            self._data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def load_devices(self) -> list[DeviceRecord]:
        if not self._enabled:
            return []
        devices_path = self._data_dir / "devices.json"
        if not devices_path.exists():
            return []
        data = json.loads(devices_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        records: list[DeviceRecord] = []
        for item in data:
            if isinstance(item, dict):
                records.append(device_record_from_dict(item))
        return records

    def load_events(self, max_events: int) -> dict[str, list[Event]]:
        if not self._enabled:
            return {}
        events_path = self._data_dir / "events.jsonl"
        if not events_path.exists():
            return {}
        events_by_device: dict[str, list[Event]] = {}
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
            events = events_by_device.setdefault(event.device_id, [])
            events.append(event)
            if len(events) > max_events:
                events_by_device[event.device_id] = events[-max_events:]
        return events_by_device

    def save_devices(self, devices: dict[str, DeviceRecord]) -> None:
        if not self._enabled:
            return
        records = [rec.to_dict() for rec in devices.values()]
        path = self._data_dir / "devices.json"
        path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)

    def append_event(self, event: Event) -> None:
        if not self._enabled:
            return
        path = self._data_dir / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json", by_alias=False)) + "\n")
        os.chmod(path, 0o600)
