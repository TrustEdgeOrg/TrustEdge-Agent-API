from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.tokens import hash_device_token


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _fmt_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


@dataclass
class DeviceRecord:
    device_id: str
    # Legacy plaintext field — migrated to device_token_hash on load/save.
    device_token: str = ""
    device_token_hash: str = ""
    token_expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_details: dict[str, Any] = field(default_factory=dict)
    last_seen_at: datetime | None = None

    def ensure_token_hash(self, *, pepper: str = "") -> None:
        """Migrate legacy plaintext tokens to hash-only storage."""
        if self.device_token_hash:
            self.device_token = ""
            return
        if self.device_token:
            self.device_token_hash = hash_device_token(self.device_token, pepper=pepper)
            self.device_token = ""

    def to_dict(self) -> dict[str, Any]:
        # Never persist plaintext device_token.
        out: dict[str, Any] = {
            "device_id": self.device_id,
            "device_token_hash": self.device_token_hash,
        }
        if self.last_details:
            out["last_details"] = self.last_details
        if self.last_seen_at is not None:
            out["last_seen_at"] = _fmt_dt(self.last_seen_at)
        if self.token_expires_at is not None:
            out["token_expires_at"] = _fmt_dt(self.token_expires_at)
        if self.revoked_at is not None:
            out["revoked_at"] = _fmt_dt(self.revoked_at)
        return out


def device_record_from_dict(data: dict[str, Any]) -> DeviceRecord:
    details = data.get("last_details")
    return DeviceRecord(
        device_id=str(data.get("device_id") or ""),
        device_token=str(data.get("device_token") or ""),
        device_token_hash=str(data.get("device_token_hash") or ""),
        token_expires_at=_parse_dt(data.get("token_expires_at")),
        revoked_at=_parse_dt(data.get("revoked_at")),
        last_details=details if isinstance(details, dict) else {},
        last_seen_at=_parse_dt(data.get("last_seen_at")),
    )
