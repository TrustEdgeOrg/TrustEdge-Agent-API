import pytest


@pytest.fixture(autouse=True)
def clear_settings_cache():
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def fakeredis() -> str:
    import fakeredis

    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=False)
    client.ping()

    import app.redis_live as redis_live_mod

    original = redis_live_mod.redis.from_url

    def _from_url(url: str, **kwargs):  # type: ignore[no-untyped-def]
        return client

    redis_live_mod.redis.from_url = _from_url
    try:
        yield "redis://fake/0"
    finally:
        redis_live_mod.redis.from_url = original
