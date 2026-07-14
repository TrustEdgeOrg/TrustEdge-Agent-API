from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import router
from app.config import get_settings
from app.store.event_store import EventStore

LOG = logging.getLogger("trustedge-agent-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_production()
    store = EventStore.from_settings(settings)
    app.state.store = store
    kafka_note = "on" if store.kafka_enabled else "off"
    LOG.info(
        "listening (disk=%s kafka=%s)",
        settings.persist_files(),
        kafka_note,
    )
    try:
        yield
    finally:
        store.close()


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="trustedge-agent-api: %(message)s")
    app = FastAPI(title="TrustEdge Agent API", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    settings.validate_production()
    host, port = settings.uvicorn_bind()
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
