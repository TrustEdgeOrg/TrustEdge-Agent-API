from __future__ import annotations

from datetime import datetime, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_event_id(ts: datetime) -> str:
    ts = ts.astimezone(timezone.utc)
    frac = f"{ts.microsecond * 1000:09d}"
    return f"evt_{ts.strftime('%Y%m%dT%H%M%S')}.{frac}"
