from __future__ import annotations

from typing import Protocol

from app.models.schemas import Event


class Publisher(Protocol):
    def publish_event(self, event: Event) -> None: ...

    def close(self) -> None: ...
