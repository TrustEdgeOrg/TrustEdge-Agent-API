from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from starlette.responses import PlainTextResponse, Response

from app.api.errors import plain_error
from app.config import Settings, get_settings
from app.core.auth import bearer_token
from app.core.constants import ERR_NOT_FOUND, ERR_UNAUTHORIZED
from app.dependencies import get_store
from app.models.schemas import RegisterResponse
from app.store.event_store import EventStore

router = APIRouter()


def _enroll_ok(request: Request, settings: Settings) -> bool:
    expected = (settings.enroll_token or "").strip()
    if not expected:
        # When enroll is unset (dev), allow revoke for local ops.
        return True
    return bearer_token(request) == expected


@router.post("/devices/{device_id}/revoke", response_model=None)
async def revoke_device(
    device_id: str,
    request: Request,
    store: EventStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> Response | PlainTextResponse:
    """Revoke a device's upload credentials (enroll bearer when configured)."""
    if not _enroll_ok(request, settings):
        return plain_error(ERR_UNAUTHORIZED, 401)
    if not store.revoke_device(device_id):
        return plain_error(ERR_NOT_FOUND, 404)
    return Response(status_code=204)


@router.post("/devices/rotate", response_model=RegisterResponse)
async def rotate_device_token(
    request: Request,
    store: EventStore = Depends(get_store),
) -> RegisterResponse | PlainTextResponse:
    """Rotate the caller's device token; requires current device bearer."""
    token = bearer_token(request)
    if not token:
        return plain_error(ERR_UNAUTHORIZED, 401)
    rotated = store.rotate_token(token)
    if rotated is None:
        return plain_error(ERR_UNAUTHORIZED, 401)
    return rotated
