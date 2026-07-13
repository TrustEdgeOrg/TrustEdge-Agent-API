from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env(primary: str, fallback: str = "") -> str:
    return os.getenv(primary, "").strip() or fallback


def _env_bool(primary: str) -> bool:
    raw = _env(primary).lower()
    return raw in {"1", "true", "yes", "on"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    listen: str = Field(default=":8080", validation_alias="TRUSTEDGE_AGENT_LISTEN")
    enroll_token: str = Field(default="", validation_alias="TRUSTEDGE_AGENT_ENROLL_TOKEN")
    data_dir: str = Field(default="data", validation_alias="TRUSTEDGE_AGENT_DATA_DIR")
    max_events: int = 500
    production: bool = Field(default=False, validation_alias="TRUSTEDGE_AGENT_PRODUCTION")
    kafka_brokers: str = Field(default="", validation_alias="KAFKA_BROKERS")
    kafka_topic: str = Field(default="trustedge.agent.events", validation_alias="KAFKA_TOPIC")
    persist_files_override: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def load_env_defaults(cls, data: dict) -> dict:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if "listen" not in out:
            out["listen"] = _env("TRUSTEDGE_AGENT_LISTEN", ":8080")
        if "enroll_token" not in out:
            out["enroll_token"] = _env("TRUSTEDGE_AGENT_ENROLL_TOKEN")
        if "data_dir" not in out:
            out["data_dir"] = _env("TRUSTEDGE_AGENT_DATA_DIR", "data")
        if "production" not in out:
            out["production"] = _env_bool("TRUSTEDGE_AGENT_PRODUCTION")
        if "kafka_brokers" not in out:
            out["kafka_brokers"] = _env("KAFKA_BROKERS")
        if "kafka_topic" not in out:
            out["kafka_topic"] = _env("KAFKA_TOPIC", fallback="trustedge.agent.events")
        if "persist_files_override" not in out:
            if "TRUSTEDGE_AGENT_PERSIST_FILES" in os.environ:
                out["persist_files_override"] = os.environ["TRUSTEDGE_AGENT_PERSIST_FILES"]
        return out

    @field_validator("production", mode="before")
    @classmethod
    def parse_production(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def persist_files(self) -> bool:
        if self.persist_files_override is not None:
            value = self.persist_files_override.strip().lower()
            if value in {"1", "true", "yes", "on"}:
                return True
            if value in {"0", "false", "no", "off"}:
                return False
        return True

    def validate_production(self) -> None:
        if not self.production:
            return
        if not self.enroll_token.strip():
            raise ValueError("production requires TRUSTEDGE_AGENT_ENROLL_TOKEN on the API")

    def uvicorn_bind(self) -> tuple[str, int]:
        listen = self.listen.strip() or ":8080"
        if listen.startswith(":"):
            return "0.0.0.0", int(listen[1:])
        if ":" in listen:
            host, port = listen.rsplit(":", 1)
            return host or "0.0.0.0", int(port)
        return "0.0.0.0", int(listen)


@lru_cache
def get_settings() -> Settings:
    return Settings()
