#!/usr/bin/env python3
"""HMAC-SHA256 sign and verify helpers."""
import hashlib
import hmac


def signState(payloadBytes: bytes, secret: str) -> str:
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    return hmac.new(key, payloadBytes, hashlib.sha256).hexdigest()


def verifySignature(payloadBytes: bytes, signature: str, secret: str) -> bool:
    return hmac.compare_digest(signState(payloadBytes, secret), signature or "")
