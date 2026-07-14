from __future__ import annotations

import json
from typing import Union

from fastapi import APIRouter, Depends
from starlette.responses import PlainTextResponse, Response

from app.api.errors import plain_error
from app.core.constants import ERR_NOT_FOUND
from app.dependencies import get_store
from app.store.event_store import EventStore

router = APIRouter()


@router.get("/clients/{device_id}", response_model=None)
def get_client(
    device_id: str,
    store: EventStore = Depends(get_store),
) -> Union[Response, PlainTextResponse]:
    view = store.get_client(device_id, 50)
    if view is None:
        return plain_error(ERR_NOT_FOUND, 404)
    return Response(
        content=json.dumps(view.model_dump(mode="json", by_alias=False)),
        status_code=200,
        media_type="application/json",
    )
