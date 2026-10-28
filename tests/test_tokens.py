from __future__ import annotations

from app.core.tokens import hash_device_token, token_digest_equal


def test_hash_stable_without_pepper() -> None:
    a = hash_device_token("tok_abc")
    b = hash_device_token("tok_abc")
    assert a == b
    assert len(a) == 64


def test_pepper_changes_digest() -> None:
    plain = hash_device_token("tok_abc")
    peppered = hash_device_token("tok_abc", pepper="secret")
    assert plain != peppered
    assert token_digest_equal(peppered, hash_device_token("tok_abc", pepper="secret"))
