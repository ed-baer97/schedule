"""JWT cookie session helpers; password helpers re-exported from app.passwords."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.config import Config
from app.passwords import hash_password, verify_password

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
]


def create_access_token(*, user_id: int, role: str, school_id: int | None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "school_id": school_id,
        "iat": now,
        "exp": now + timedelta(hours=Config.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
