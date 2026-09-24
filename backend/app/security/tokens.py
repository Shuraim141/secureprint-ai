"""JWT creation/validation with PyJWT. Pure functions: secret and algorithm are parameters.

The role claim is informational only. Authorization always uses the role stored in the
database, so a role change or account disable takes effect immediately.
Production: OIDC tokens issued by an enterprise IdP; this module becomes a token validator.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt


class TokenError(Exception):
    """Raised for any invalid, expired or malformed token (message is safe to show)."""


def create_access_token(
    *, subject: str, role: str, secret: str, algorithm: str, expires_minutes: int
) -> tuple[str, str, datetime]:
    """Return (token, jti, expires_at)."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expires_minutes)
    jti = uuid.uuid4().hex
    payload = {
        "sub": subject, "role": role, "jti": jti, "type": "access", "iat": now, "exp": expires_at,
    }
    return jwt.encode(payload, secret, algorithm=algorithm), jti, expires_at


def decode_access_token(token: str, *, secret: str, algorithm: str) -> dict:
    try:
        payload = jwt.decode(
            token, secret, algorithms=[algorithm],  # explicit allow-list blocks alg=none
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token") from exc
    if payload.get("type") != "access":
        raise TokenError("Invalid token type")
    return payload
