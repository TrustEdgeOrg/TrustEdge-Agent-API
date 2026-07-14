from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends, Request

from starlette.responses import PlainTextResponse

from app.api.errors import plain_error
from app.config import Settings, get_settings
from app.core.auth import bearer_token
from app.core.constants import ERR_BAD_REQUEST, ERR_INTERNAL, ERR_INVALID_JSON, ERR_UNAUTHORIZED
from app.dependencies import get_store
from app.models.schemas import RegisterRequest, RegisterResponse
from app.store.event_store import EventStore

router = APIRouter()


@router.post("/register", response_model=None)
async def register(
    request: Request,
    settings: Settings = Depends(get_settings),
    store: EventStore = Depends(get_store),
) -> Union[RegisterResponse, PlainTextResponse]:
    if settings.enroll_token and bearer_token(request) != settings.enroll_token:
        return plain_error(ERR_UNAUTHORIZED, 401)

    body = await request.body()
    if len(body) > 1 << 20:
        return plain_error(ERR_BAD_REQUEST, 400)
    req = RegisterRequest()
    if body:
        try:
            req = RegisterRequest.model_validate_json(body)
        except ValueError:
            return plain_error(ERR_INVALID_JSON, 400)

    try:
        return store.register(req)
    except OSError:
        return plain_error(ERR_INTERNAL, 500)
