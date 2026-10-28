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
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    listen: str = Field(default=":8080", validation_alias="TRUSTEDGE_AGENT_LISTEN")
    enroll_token: str = Field(default="", validation_alias="TRUSTEDGE_AGENT_ENROLL_TOKEN")
    data_dir: str = Field(default="data", validation_alias="TRUSTEDGE_AGENT_DATA_DIR")
    max_events: int = 500
    production: bool = Field(default=False, validation_alias="TRUSTEDGE_AGENT_PRODUCTION")
    kafka_brokers: str = Field(default="", validation_alias="KAFKA_BROKERS")
    kafka_topic: str = Field(default="trustedge.agent.events", validation_alias="KAFKA_TOPIC")
    redis_url: str = Field(default="", validation_alias="REDIS_URL")
    persist_files_override: Optional[str] = None
    trustedge_backend_url: str = Field(default="", validation_alias="TRUSTEDGE_BACKEND_URL")
    trustedge_ingest_token: str = Field(default="", validation_alias="TRUSTEDGE_INGEST_TOKEN")
    trustedge_upsert_timeout_sec: float = Field(
        default=5.0, validation_alias="TRUSTEDGE_UPSERT_TIMEOUT_SEC"
    )
    # Optional HMAC pepper for device-token digests (empty = plain SHA-256).
    device_token_pepper: str = Field(default="", validation_alias="TRUSTEDGE_DEVICE_TOKEN_PEPPER")
    # 0 disables expiry. When set, register/rotate stamps token_expires_at.
    device_token_ttl_sec: int = Field(default=0, validation_alias="TRUSTEDGE_DEVICE_TOKEN_TTL_SEC")
    # Shared Postgres URL for token_hash → device_id (multi-replica). Empty = in-memory/local.
    device_creds_database_url: str = Field(
        default="", validation_alias="TRUSTEDGE_AGENT_DEVICE_CREDS_DATABASE_URL"
    )
    # Dedicated Redis for auth cache (do not share with twin REDIS_URL).
    device_creds_redis_url: str = Field(
        default="", validation_alias="TRUSTEDGE_AGENT_DEVICE_CREDS_REDIS_URL"
    )
    # TTL for cached token_hash → device_id entries (seconds).
    device_creds_cache_ttl_sec: int = Field(
        default=300, validation_alias="TRUSTEDGE_AGENT_DEVICE_CREDS_CACHE_TTL_SEC"
    )

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
        if "redis_url" not in out and "REDIS_URL" not in out:
            redis_url = _env("REDIS_URL")
            out["redis_url"] = redis_url
            out["REDIS_URL"] = redis_url
        if "trustedge_backend_url" not in out and "TRUSTEDGE_BACKEND_URL" not in out:
            backend_url = _env("TRUSTEDGE_BACKEND_URL")
            out["trustedge_backend_url"] = backend_url
            out["TRUSTEDGE_BACKEND_URL"] = backend_url
        # Set both field name and validation alias — pydantic-settings matches the alias.
        ingest_token = (
            str(out.get("trustedge_ingest_token") or out.get("TRUSTEDGE_INGEST_TOKEN") or "")
            .strip()
            or _env("TRUSTEDGE_INGEST_TOKEN")
        )
        out["trustedge_ingest_token"] = ingest_token
        out["TRUSTEDGE_INGEST_TOKEN"] = ingest_token
        if "trustedge_upsert_timeout_sec" not in out and "TRUSTEDGE_UPSERT_TIMEOUT_SEC" not in out:
            raw_timeout = _env("TRUSTEDGE_UPSERT_TIMEOUT_SEC", "5")
            try:
                out["trustedge_upsert_timeout_sec"] = float(raw_timeout)
            except ValueError:
                out["trustedge_upsert_timeout_sec"] = 5.0
        if "persist_files_override" not in out:
            if "TRUSTEDGE_AGENT_PERSIST_FILES" in os.environ:
                out["persist_files_override"] = os.environ["TRUSTEDGE_AGENT_PERSIST_FILES"]
        if "device_token_pepper" not in out and "TRUSTEDGE_DEVICE_TOKEN_PEPPER" not in out:
            pepper = _env("TRUSTEDGE_DEVICE_TOKEN_PEPPER")
            out["device_token_pepper"] = pepper
            out["TRUSTEDGE_DEVICE_TOKEN_PEPPER"] = pepper
        if "device_token_ttl_sec" not in out and "TRUSTEDGE_DEVICE_TOKEN_TTL_SEC" not in out:
            raw_ttl = _env("TRUSTEDGE_DEVICE_TOKEN_TTL_SEC", "0")
            try:
                out["device_token_ttl_sec"] = int(raw_ttl)
            except ValueError:
                out["device_token_ttl_sec"] = 0
        if (
            "device_creds_database_url" not in out
            and "TRUSTEDGE_AGENT_DEVICE_CREDS_DATABASE_URL" not in out
        ):
            creds_url = _env("TRUSTEDGE_AGENT_DEVICE_CREDS_DATABASE_URL")
            out["device_creds_database_url"] = creds_url
            out["TRUSTEDGE_AGENT_DEVICE_CREDS_DATABASE_URL"] = creds_url
        if (
            "device_creds_redis_url" not in out
            and "TRUSTEDGE_AGENT_DEVICE_CREDS_REDIS_URL" not in out
        ):
            creds_redis = _env("TRUSTEDGE_AGENT_DEVICE_CREDS_REDIS_URL")
            out["device_creds_redis_url"] = creds_redis
            out["TRUSTEDGE_AGENT_DEVICE_CREDS_REDIS_URL"] = creds_redis
        if (
            "device_creds_cache_ttl_sec" not in out
            and "TRUSTEDGE_AGENT_DEVICE_CREDS_CACHE_TTL_SEC" not in out
        ):
            raw_cache_ttl = _env("TRUSTEDGE_AGENT_DEVICE_CREDS_CACHE_TTL_SEC", "300")
            try:
                out["device_creds_cache_ttl_sec"] = int(raw_cache_ttl)
            except ValueError:
                out["device_creds_cache_ttl_sec"] = 300
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
