"""Shared device-credential store for multi-replica Agent-API.

When TRUSTEDGE_AGENT_DEVICE_CREDS_DATABASE_URL is set, token_hash → device_id
lives in Postgres (source of truth). Optional Redis (TRUSTEDGE_AGENT_DEVICE_CREDS_REDIS_URL)
caches lookups; writes always go to Postgres and invalidate/update cache.
Empty Redis URL = Postgres-only (recommended default).
Plaintext device tokens are never stored.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

LOG = logging.getLogger("trustedge-agent-api")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_device_credentials (
    device_id TEXT PRIMARY KEY,
    token_hash TEXT,
    token_expires_at TIMESTAMPTZ NULL,
    revoked_at TIMESTAMPTZ NULL,
    last_seen_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS agent_device_credentials_token_hash_uidx
    ON agent_device_credentials (token_hash)
    WHERE token_hash IS NOT NULL AND token_hash <> '';
"""

TOKEN_KEY_FMT = "device_creds:token:{token_hash}"
DEVICE_HASH_KEY_FMT = "device_creds:device:{device_id}:hash"


@dataclass
class DeviceCredRow:
    device_id: str
    token_hash: str = ""
    token_expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_seen_at: datetime | None = None


class DeviceCredsBackend(Protocol):
    def ensure_schema(self) -> None: ...

    def upsert_active(
        self,
        device_id: str,
        *,
        token_hash: str,
        token_expires_at: datetime | None,
        last_seen_at: datetime | None,
    ) -> None: ...

    def lookup_active_device_id(self, token_hash: str) -> str | None: ...

    def get(self, device_id: str) -> DeviceCredRow | None: ...

    def revoke(self, device_id: str, *, revoked_at: datetime) -> bool: ...

    def touch_last_seen(self, device_id: str, *, last_seen_at: datetime) -> None: ...

    def close(self) -> None: ...


class PostgresDeviceCreds:
    """Postgres-backed credential map shared by Agent-API replicas."""

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "psycopg is required for TRUSTEDGE_AGENT_DEVICE_CREDS_DATABASE_URL; "
                "pip install 'psycopg[binary]'"
            ) from exc
        self._psycopg = psycopg
        self._conn = psycopg.connect(database_url, autocommit=True)

    def ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        LOG.info("device credentials schema ready (postgres)")

    def upsert_active(
        self,
        device_id: str,
        *,
        token_hash: str,
        token_expires_at: datetime | None,
        last_seen_at: datetime | None,
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_device_credentials (
                    device_id, token_hash, token_expires_at, revoked_at, last_seen_at, updated_at
                ) VALUES (%s, %s, %s, NULL, %s, NOW())
                ON CONFLICT (device_id) DO UPDATE SET
                    token_hash = EXCLUDED.token_hash,
                    token_expires_at = EXCLUDED.token_expires_at,
                    revoked_at = NULL,
                    last_seen_at = EXCLUDED.last_seen_at,
                    updated_at = NOW()
                """,
                (device_id, token_hash, token_expires_at, last_seen_at),
            )

    def lookup_active_device_id(self, token_hash: str) -> str | None:
        if not token_hash:
            return None
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT device_id
                FROM agent_device_credentials
                WHERE token_hash = %s
                  AND revoked_at IS NULL
                  AND (token_expires_at IS NULL OR token_expires_at > NOW())
                """,
                (token_hash,),
            )
            row = cur.fetchone()
        return str(row[0]) if row else None

    def get(self, device_id: str) -> DeviceCredRow | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT device_id, token_hash, token_expires_at, revoked_at, last_seen_at
                FROM agent_device_credentials
                WHERE device_id = %s
                """,
                (device_id.strip(),),
            )
            row = cur.fetchone()
        if not row:
            return None
        return DeviceCredRow(
            device_id=str(row[0]),
            token_hash=str(row[1] or ""),
            token_expires_at=row[2],
            revoked_at=row[3],
            last_seen_at=row[4],
        )

    def revoke(self, device_id: str, *, revoked_at: datetime) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_device_credentials
                SET token_hash = NULL,
                    token_expires_at = NULL,
                    revoked_at = %s,
                    updated_at = NOW()
                WHERE device_id = %s
                """,
                (revoked_at, device_id.strip()),
            )
            return cur.rowcount > 0

    def touch_last_seen(self, device_id: str, *, last_seen_at: datetime) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_device_credentials
                SET last_seen_at = %s, updated_at = NOW()
                WHERE device_id = %s
                """,
                (last_seen_at, device_id.strip()),
            )

    def close(self) -> None:
        self._conn.close()


class MemoryDeviceCreds:
    """In-process credential map (single-node / tests)."""

    def __init__(self) -> None:
        self._by_device: dict[str, DeviceCredRow] = {}
        self._by_hash: dict[str, str] = {}

    def ensure_schema(self) -> None:
        return None

    def upsert_active(
        self,
        device_id: str,
        *,
        token_hash: str,
        token_expires_at: datetime | None,
        last_seen_at: datetime | None,
    ) -> None:
        prev = self._by_device.get(device_id)
        if prev and prev.token_hash:
            self._by_hash.pop(prev.token_hash, None)
        row = DeviceCredRow(
            device_id=device_id,
            token_hash=token_hash,
            token_expires_at=token_expires_at,
            revoked_at=None,
            last_seen_at=last_seen_at,
        )
        self._by_device[device_id] = row
        if token_hash:
            self._by_hash[token_hash] = device_id

    def lookup_active_device_id(self, token_hash: str) -> str | None:
        if not token_hash:
            return None
        device_id = self._by_hash.get(token_hash)
        if not device_id:
            return None
        row = self._by_device.get(device_id)
        if row is None or row.revoked_at is not None:
            return None
        if row.token_hash != token_hash:
            return None
        if row.token_expires_at is not None:
            from app.core import clock as clock_mod

            if row.token_expires_at <= clock_mod.now_utc():
                return None
        return device_id

    def get(self, device_id: str) -> DeviceCredRow | None:
        return self._by_device.get(device_id.strip())

    def revoke(self, device_id: str, *, revoked_at: datetime) -> bool:
        row = self._by_device.get(device_id.strip())
        if row is None:
            return False
        if row.token_hash:
            self._by_hash.pop(row.token_hash, None)
        row.token_hash = ""
        row.token_expires_at = None
        row.revoked_at = revoked_at
        return True

    def touch_last_seen(self, device_id: str, *, last_seen_at: datetime) -> None:
        row = self._by_device.get(device_id.strip())
        if row is not None:
            row.last_seen_at = last_seen_at

    def close(self) -> None:
        return None


class CachedDeviceCreds:
    """Durable backend + Redis cache for fast auth lookups.

    Cache miss / Redis errors fall through to the durable backend.
    Auth is never fail-open: if both cache and backend miss, lookup returns None.
    """

    def __init__(
        self,
        inner: DeviceCredsBackend,
        *,
        redis_url: str,
        cache_ttl_sec: int = 300,
        redis_client: Any | None = None,
    ) -> None:
        self._inner = inner
        self._redis_url = (redis_url or "").strip()
        self._cache_ttl_sec = max(1, int(cache_ttl_sec or 300))
        self._client: Any = redis_client

    def ensure_schema(self) -> None:
        self._inner.ensure_schema()

    def _redis(self) -> Any | None:
        if self._client is not None:
            return self._client
        if not self._redis_url:
            return None
        try:
            import redis

            client = redis.Redis.from_url(self._redis_url, decode_responses=True)
            client.ping()
            self._client = client
            return client
        except Exception as exc:  # noqa: BLE001 — fall through to durable store
            LOG.warning("device creds redis cache unavailable: %s", exc)
            self._client = None
            return None

    def _cache_ttl(self, token_expires_at: datetime | None) -> int:
        if token_expires_at is None:
            return self._cache_ttl_sec
        from app.core import clock as clock_mod

        remaining = int((token_expires_at - clock_mod.now_utc()).total_seconds())
        if remaining <= 0:
            return 1
        return max(1, min(self._cache_ttl_sec, remaining))

    def _cache_set(
        self,
        *,
        device_id: str,
        token_hash: str,
        token_expires_at: datetime | None,
        previous_hash: str = "",
    ) -> None:
        client = self._redis()
        if client is None or not token_hash:
            return
        try:
            pipe = client.pipeline()
            if previous_hash and previous_hash != token_hash:
                pipe.delete(TOKEN_KEY_FMT.format(token_hash=previous_hash))
            ttl = self._cache_ttl(token_expires_at)
            pipe.set(TOKEN_KEY_FMT.format(token_hash=token_hash), device_id, ex=ttl)
            pipe.set(DEVICE_HASH_KEY_FMT.format(device_id=device_id), token_hash, ex=ttl)
            pipe.execute()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("device creds redis cache set failed: %s", exc)
            if self._redis_url:
                self._client = None

    def _cache_delete(self, *, device_id: str, token_hash: str = "") -> None:
        client = self._redis()
        if client is None:
            return
        try:
            keys = [DEVICE_HASH_KEY_FMT.format(device_id=device_id)]
            hash_to_drop = token_hash
            if not hash_to_drop:
                hash_to_drop = client.get(DEVICE_HASH_KEY_FMT.format(device_id=device_id)) or ""
            if hash_to_drop:
                keys.append(TOKEN_KEY_FMT.format(token_hash=hash_to_drop))
            if keys:
                client.delete(*keys)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("device creds redis cache delete failed: %s", exc)
            if self._redis_url:
                self._client = None

    def upsert_active(
        self,
        device_id: str,
        *,
        token_hash: str,
        token_expires_at: datetime | None,
        last_seen_at: datetime | None,
    ) -> None:
        previous_hash = ""
        prev = self._inner.get(device_id)
        if prev and prev.token_hash:
            previous_hash = prev.token_hash
        self._inner.upsert_active(
            device_id,
            token_hash=token_hash,
            token_expires_at=token_expires_at,
            last_seen_at=last_seen_at,
        )
        self._cache_set(
            device_id=device_id,
            token_hash=token_hash,
            token_expires_at=token_expires_at,
            previous_hash=previous_hash,
        )

    def lookup_active_device_id(self, token_hash: str) -> str | None:
        if not token_hash:
            return None
        client = self._redis()
        if client is not None:
            try:
                cached = client.get(TOKEN_KEY_FMT.format(token_hash=token_hash))
                if cached:
                    return str(cached)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("device creds redis cache get failed: %s", exc)
                if self._redis_url:
                    self._client = None
        device_id = self._inner.lookup_active_device_id(token_hash)
        if device_id:
            row = self._inner.get(device_id)
            self._cache_set(
                device_id=device_id,
                token_hash=token_hash,
                token_expires_at=row.token_expires_at if row else None,
            )
        return device_id

    def get(self, device_id: str) -> DeviceCredRow | None:
        return self._inner.get(device_id)

    def revoke(self, device_id: str, *, revoked_at: datetime) -> bool:
        prev = self._inner.get(device_id)
        ok = self._inner.revoke(device_id, revoked_at=revoked_at)
        self._cache_delete(
            device_id=device_id,
            token_hash=(prev.token_hash if prev else ""),
        )
        return ok

    def touch_last_seen(self, device_id: str, *, last_seen_at: datetime) -> None:
        self._inner.touch_last_seen(device_id, last_seen_at=last_seen_at)

    def close(self) -> None:
        self._inner.close()
        self._client = None


def device_creds_from_settings(settings: Any) -> DeviceCredsBackend:
    pg_url = (getattr(settings, "device_creds_database_url", None) or "").strip()
    if not pg_url:
        return MemoryDeviceCreds()

    backend: DeviceCredsBackend = PostgresDeviceCreds(pg_url)
    backend.ensure_schema()

    # Auth cache uses its own Redis — never the live-twin REDIS_URL.
    redis_url = (getattr(settings, "device_creds_redis_url", None) or "").strip()
    if redis_url:
        cache_ttl = int(getattr(settings, "device_creds_cache_ttl_sec", 300) or 300)
        LOG.info("device credentials cache enabled (dedicated redis)")
        return CachedDeviceCreds(backend, redis_url=redis_url, cache_ttl_sec=cache_ttl)
    LOG.info("device credentials postgres enabled (no auth redis cache)")
    return backend
