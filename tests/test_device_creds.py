from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.core.tokens import hash_device_token
from app.models.schemas import RegisterRequest
from app.store.device_creds import (
    DEVICE_HASH_KEY_FMT,
    TOKEN_KEY_FMT,
    CachedDeviceCreds,
    MemoryDeviceCreds,
)
from app.store.event_store import EventStore


class _FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._ops: list[tuple] = []

    def delete(self, *keys: str) -> "_FakePipeline":
        self._ops.append(("delete", keys))
        return self

    def set(self, key: str, value: str, ex: int | None = None) -> "_FakePipeline":
        self._ops.append(("set", key, value, ex))
        return self

    def execute(self) -> list:
        results = []
        for op in self._ops:
            if op[0] == "delete":
                results.append(self._redis.delete(*op[1]))
            elif op[0] == "set":
                results.append(self._redis.set(op[1], op[2], ex=op[3]))
        self._ops.clear()
        return results


class FakeRedis:
    """Minimal Redis stand-in for CachedDeviceCreds unit tests."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.gets = 0

    def get(self, key: str) -> str | None:
        self.gets += 1
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.data[key] = value
        return True

    def delete(self, *keys: str) -> int:
        n = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                n += 1
        return n

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)


def test_shared_memory_creds_across_stores(tmp_path) -> None:
    """Two EventStore instances share the same creds backend (replica simulation)."""
    shared = MemoryDeviceCreds()
    s1 = Settings(data_dir=str(tmp_path / "a"), production=False, persist_files_override="0")
    s2 = Settings(data_dir=str(tmp_path / "b"), production=False, persist_files_override="0")
    store1 = EventStore(s1, creds=shared)
    store2 = EventStore(s2, creds=shared)
    try:
        reg = store1.register(RegisterRequest(hostname="shared-host"))
        assert store2.device_id_for_token(reg.device_token) == reg.device_id
        rotated = store2.rotate_token(reg.device_token)
        assert rotated is not None
        assert store1.device_id_for_token(reg.device_token) is None
        assert store1.device_id_for_token(rotated.device_token) == reg.device_id
    finally:
        store1.close()
        store2.close()


def test_memory_creds_revoke_visible_to_peer(tmp_path) -> None:
    shared = MemoryDeviceCreds()
    s1 = Settings(data_dir=str(tmp_path / "a"), production=False, persist_files_override="0")
    s2 = Settings(data_dir=str(tmp_path / "b"), production=False, persist_files_override="0")
    store1 = EventStore(s1, creds=shared)
    store2 = EventStore(s2, creds=shared)
    try:
        reg = store1.register(RegisterRequest(hostname="rev-host"))
        assert store2.revoke_device(reg.device_id) is True
        assert store1.device_id_for_token(reg.device_token) is None
    finally:
        store1.close()
        store2.close()


def test_memory_creds_respects_ttl(tmp_path) -> None:
    shared = MemoryDeviceCreds()
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        production=False,
        persist_files_override="0",
        device_token_ttl_sec=60,
    )
    store = EventStore(settings, creds=shared)
    try:
        reg = store.register(RegisterRequest(hostname="ttl"))
        row = shared.get(reg.device_id)
        assert row is not None
        row.token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert store.device_id_for_token(reg.device_token) is None
    finally:
        store.close()


def test_cached_creds_hit_and_miss() -> None:
    inner = MemoryDeviceCreds()
    fake = FakeRedis()
    cached = CachedDeviceCreds(inner, redis_url="", redis_client=fake, cache_ttl_sec=60)
    token_hash = "abc123"
    inner.upsert_active(
        "dev_1",
        token_hash=token_hash,
        token_expires_at=None,
        last_seen_at=None,
    )

    # Miss → durable → populate cache
    assert cached.lookup_active_device_id(token_hash) == "dev_1"
    assert fake.data[TOKEN_KEY_FMT.format(token_hash=token_hash)] == "dev_1"

    # Hit → no need to re-read durable (we still may get; verify cache path)
    gets_before = fake.gets
    assert cached.lookup_active_device_id(token_hash) == "dev_1"
    assert fake.gets == gets_before + 1


def test_cached_creds_rotate_invalidates_old_hash(tmp_path) -> None:
    inner = MemoryDeviceCreds()
    fake = FakeRedis()
    cached = CachedDeviceCreds(inner, redis_url="", redis_client=fake, cache_ttl_sec=60)
    settings = Settings(data_dir=str(tmp_path / "data"), production=False, persist_files_override="0")
    store = EventStore(settings, creds=cached)
    try:
        reg = store.register(RegisterRequest(hostname="cache-rot"))
        old_hash = hash_device_token(reg.device_token, pepper="")
        assert cached.lookup_active_device_id(old_hash) == reg.device_id
        assert TOKEN_KEY_FMT.format(token_hash=old_hash) in fake.data

        rotated = store.rotate_token(reg.device_token)
        assert rotated is not None
        new_hash = hash_device_token(rotated.device_token, pepper="")
        assert TOKEN_KEY_FMT.format(token_hash=old_hash) not in fake.data
        assert fake.data[TOKEN_KEY_FMT.format(token_hash=new_hash)] == reg.device_id
        assert store.device_id_for_token(reg.device_token) is None
        assert store.device_id_for_token(rotated.device_token) == reg.device_id
    finally:
        store.close()


def test_cached_creds_revoke_clears_cache(tmp_path) -> None:
    inner = MemoryDeviceCreds()
    fake = FakeRedis()
    cached = CachedDeviceCreds(inner, redis_url="", redis_client=fake, cache_ttl_sec=60)
    settings = Settings(data_dir=str(tmp_path / "data"), production=False, persist_files_override="0")
    store = EventStore(settings, creds=cached)
    try:
        reg = store.register(RegisterRequest(hostname="cache-rev"))
        token_hash = hash_device_token(reg.device_token, pepper="")
        assert cached.lookup_active_device_id(token_hash) == reg.device_id
        assert store.revoke_device(reg.device_id) is True
        assert TOKEN_KEY_FMT.format(token_hash=token_hash) not in fake.data
        assert DEVICE_HASH_KEY_FMT.format(device_id=reg.device_id) not in fake.data
        assert store.device_id_for_token(reg.device_token) is None
    finally:
        store.close()


def test_cached_creds_redis_down_falls_through() -> None:
    class BrokenRedis:
        def get(self, key: str) -> str | None:
            raise RuntimeError("down")

        def pipeline(self):
            raise RuntimeError("down")

        def delete(self, *keys: str) -> int:
            raise RuntimeError("down")

    inner = MemoryDeviceCreds()
    inner.upsert_active(
        "dev_x",
        token_hash="hash_x",
        token_expires_at=None,
        last_seen_at=None,
    )
    cached = CachedDeviceCreds(
        inner, redis_url="redis://unused", redis_client=BrokenRedis(), cache_ttl_sec=60
    )
    assert cached.lookup_active_device_id("hash_x") == "dev_x"
