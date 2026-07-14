from __future__ import annotations

from starlette.responses import PlainTextResponse


def plain_error(message: str, status_code: int) -> PlainTextResponse:
    return PlainTextResponse(content=message, status_code=status_code)
