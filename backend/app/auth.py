"""
Authentication & authorisation.

Dev mode (default): the API mints and verifies its own HS256 tokens, so
it runs with no external IdP. Production: set auth_dev_mode=false and an
OIDC issuer — tokens are then verified as RS256 against the issuer's
JWKS. RBAC and org scoping are identical in both modes.

Roles: viewer < inspector < engineer < approver < admin.
'admin' is allowed everywhere.
"""

from __future__ import annotations

import datetime as dt
from typing import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .db import get_db

_bearer = HTTPBearer(auto_error=True)


def create_token(user: "models.User") -> str:
    """Mint a dev token. In production the IdP issues tokens, not us."""
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": user.id,
        "org_id": user.org_id,
        "role": user.role,
        "email": user.email,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def _decode(token: str) -> dict:
    if settings.auth_dev_mode:
        return jwt.decode(token, settings.jwt_secret,
                          algorithms=[settings.jwt_alg])
    # Production: verify RS256 against the IdP's JWKS.
    if not settings.oidc_issuer:
        raise HTTPException(status_code=500, detail="OIDC issuer not configured")
    jwks = jwt.PyJWKClient(f"{settings.oidc_issuer}/.well-known/jwks.json")
    signing_key = jwks.get_signing_key_from_jwt(token).key
    return jwt.decode(token, signing_key, algorithms=["RS256"],
                      audience=settings.oidc_audience, issuer=settings.oidc_issuer)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> "models.User":
    try:
        claims = _decode(creds.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Invalid token: {exc}")
    user = db.get(models.User, claims.get("sub"))
    if user is None:
        # In production you might JIT-provision from claims; for the
        # skeleton the user must already exist.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Unknown user")
    return user


def require_role(*roles: str) -> Callable:
    """Dependency factory — allow the listed roles (admin always allowed)."""
    allowed = set(roles) | {"admin"}

    def _dep(user: "models.User" = Depends(get_current_user)) -> "models.User":
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not permitted "
                       f"(need one of {sorted(allowed)})")
        return user

    return _dep
