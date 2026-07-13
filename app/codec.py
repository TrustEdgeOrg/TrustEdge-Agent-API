from __future__ import annotations

import zstandard as zstd

from app.constants import CONTENT_ENCODING_ZSTD


def is_zstd(content_encoding: str | None) -> bool:
    if not content_encoding:
        return False
    return any(part.strip().lower() == CONTENT_ENCODING_ZSTD for part in content_encoding.split(","))


def decompress(data: bytes) -> bytes:
    return zstd.ZstdDecompressor().decompress(data)
