"""Dev-only auth helper: mint a token for local testing.

Disabled when auth_dev_mode is false — production tokens come from the
real IdP, not this endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from .. import models
from ..auth import create_token
from ..config import settings
from ..db import get_db
from ..schemas import DevTokenRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/dev-token", response_model=TokenResponse)
def dev_token(body: DevTokenRequest, db: Session = Depends(get_db)):
    if not settings.auth_dev_mode:
        raise HTTPException(status_code=404, detail="Not available")

    org = db.scalar(select(models.Organization)
                    .where(models.Organization.name == body.org_name))
    if org is None:
        org = models.Organization(name=body.org_name)
        db.add(org)
        db.flush()

    user = db.scalar(
        select(models.User).where(models.User.org_id == org.id,
                                  models.User.email == body.email))
    if user is None:
        user = models.User(org_id=org.id, email=body.email, role=body.role)
        db.add(user)
    else:
        user.role = body.role
    db.commit()
    db.refresh(user)

    return TokenResponse(access_token=create_token(user), role=user.role,
                         org_id=user.org_id)
