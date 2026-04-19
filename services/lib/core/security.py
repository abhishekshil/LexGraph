"""Minimal JWT + password hashing. Kept tiny on purpose; swap for auth provider in prod."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any

from .config import settings


def _b64(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return urlsafe_b64decode(data + pad)


def _sign(payload: str) -> str:
    sig = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64(sig)


def issue_token(sub: str, claims: dict[str, Any] | None = None) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = {
        "sub": sub,
        "iat": int(time.time()),
        "exp": int(time.time()) + settings.auth_token_expires_min * 60,
        **(claims or {}),
    }
    body_enc = _b64(json.dumps(body, separators=(",", ":")).encode())
    payload = f"{header}.{body_enc}"
    return f"{payload}.{_sign(payload)}"


def verify_token(token: str) -> dict[str, Any]:
    try:
        header_b64, body_b64, sig = token.split(".")
    except ValueError as e:
        raise ValueError("malformed token") from e
    payload = f"{header_b64}.{body_b64}"
    expected = _sign(payload)
    if not hmac.compare_digest(expected, sig):
        raise ValueError("bad signature")
    body: dict[str, Any] = json.loads(_b64d(body_b64))
    if body.get("exp", 0) < int(time.time()):
        raise ValueError("expired")
    return body


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"{_b64(salt)}.{_b64(h)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, hash_b64 = stored.split(".")
    except ValueError:
        return False
    salt = _b64d(salt_b64)
    expected = _b64d(hash_b64)
    candidate = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(candidate, expected)
