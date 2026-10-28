"""Opaque device-token hashing helpers.

Device tokens are high-entropy random secrets (tok_ + 24 bytes hex). We store
only a SHA-256 digest (optionally peppered) so a devices.json leak does not
immediately yield usable bearer credentials.
"""

from __future__ import annotations

import hashlib
import hmac


def hash_device_token(token: str, *, pepper: str = "") -> str:
    """Return a hex digest for persistent storage / lookup."""
    raw = (token or "").strip().encode("utf-8")
    if not raw:
        return ""
    if pepper:
        return hmac.new(pepper.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hashlib.sha256(raw).hexdigest()


def token_digest_equal(left: str, right: str) -> bool:
    """Constant-time compare for hex digests."""
    a = (left or "").strip().encode("utf-8")
    b = (right or "").strip().encode("utf-8")
    if not a or not b or len(a) != len(b):
        return False
    return hmac.compare_digest(a, b)
