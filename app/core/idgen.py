from __future__ import annotations

import secrets


def new_device_id() -> str:
    return "dev_" + secrets.token_hex(16)


def new_token() -> str:
    return "tok_" + secrets.token_hex(24)
