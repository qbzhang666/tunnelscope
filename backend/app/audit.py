"""Audit-log helper — call on every mutation that matters for liability."""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import models


def record(db: Session, user: "models.User", entity: str, entity_id: str,
           action: str, detail: dict | None = None) -> None:
    db.add(models.AuditLog(
        org_id=user.org_id, user_id=user.id, entity=entity,
        entity_id=entity_id, action=action, detail=detail or {},
    ))
