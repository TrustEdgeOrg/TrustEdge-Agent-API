from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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


def device_record_from_dict(data: dict[str, Any]) -> DeviceRecord:
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
