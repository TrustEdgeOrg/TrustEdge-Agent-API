from __future__ import annotations

import json
import logging
from typing import Protocol

from kafka import KafkaProducer

from app.models import Event

LOG = logging.getLogger("trustedge-agent-api")
DEFAULT_TOPIC = "trustedge.agent.events"


class Publisher(Protocol):
    def publish_event(self, event: Event) -> None: ...

    def close(self) -> None: ...


class KafkaPublisher:
    def __init__(self, brokers: str, topic: str = DEFAULT_TOPIC) -> None:
        broker_list = [part.strip() for part in brokers.split(",") if part.strip()]
        if not broker_list:
            raise ValueError("kafka brokers required")
        self._topic = topic or DEFAULT_TOPIC
        self._producer = KafkaProducer(
            bootstrap_servers=broker_list,
            acks=1,
            linger_ms=5,
            value_serializer=lambda value: value,
            key_serializer=lambda value: value,
        )

    @property
    def topic(self) -> str:
        return self._topic

    def publish_event(self, event: Event) -> None:
        try:
            payload = json.dumps(event.model_dump(mode="json", by_alias=False)).encode("utf-8")
            future = self._producer.send(self._topic, key=event.device_id.encode("utf-8"), value=payload)
            future.add_errback(self._on_error, event)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("kafka publish %s %s: %s", event.device_id, event.type, exc)

    def _on_error(self, exc: Exception, event: Event) -> None:
        LOG.warning("kafka publish %s %s: %s", event.device_id, event.type, exc)

    def close(self) -> None:
        self._producer.flush(timeout=3)
        self._producer.close(timeout=3)


class NullPublisher:
    def publish_event(self, event: Event) -> None:
        return None

    def close(self) -> None:
        return None
