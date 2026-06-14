"""Defects — register, list, cost build-up, and the work-order sign-off flow."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, domain, models
from ..auth import get_current_user, require_role
from ..db import get_db
from ..schemas import DefectCreate, DefectRead, WorkOrderCreate, WorkOrderRead

router = APIRouter(tags=["defects"])


def _get_defect(db: Session, user: models.User, defect_id: str) -> models.Defect:
    d = db.get(models.Defect, defect_id)
    if d is None or d.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Defect not found")
    return d


@router.post("/defects", response_model=DefectRead, status_code=201)
def create_defect(body: DefectCreate,
                  user: models.User = Depends(require_role("inspector")),
                  db: Session = Depends(get_db)):
    tunnel = db.get(models.Tunnel, body.tunnel_id)
    if tunnel is None or tunnel.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    d = models.Defect(org_id=user.org_id, **body.model_dump())
    db.add(d)
    db.flush()
    audit.record(db, user, "defect", d.id, "create",
                 {"defect_type": d.defect_type, "tunnel_id": d.tunnel_id})
    db.commit()
    db.refresh(d)
    return d


@router.get("/defects", response_model=list[DefectRead])
def list_defects(tunnel_id: str | None = None,
                 user: models.User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    q = select(models.Defect).where(models.Defect.org_id == user.org_id)
    if tunnel_id:
        q = q.where(models.Defect.tunnel_id == tunnel_id)
    return db.scalars(q).all()


@router.get("/defects/{defect_id}", response_model=DefectRead)
def get_defect(defect_id: str,
               user: models.User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    return _get_defect(db, user, defect_id)


@router.get("/defects/{defect_id}/cost")
def defect_cost(defect_id: str,
                user: models.User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Transparent cost build-up — reuses utils.cost_model unchanged."""
    d = _get_defect(db, user, defect_id)
    return domain.estimate_cost(d)


# ---- work orders (the engineer sign-off + audit surface) --------------------
@router.post("/defects/{defect_id}/work-order", response_model=WorkOrderRead,
             status_code=201)
def create_work_order(defect_id: str, body: WorkOrderCreate,
                      user: models.User = Depends(require_role("engineer")),
                      db: Session = Depends(get_db)):
    d = _get_defect(db, user, defect_id)
    wo = models.Intervention(org_id=user.org_id, defect_id=d.id,
                             steps=body.steps, deadline_days=body.deadline_days)
    db.add(wo)
    db.flush()
    audit.record(db, user, "work_order", wo.id, "create", {"defect_id": d.id})
    db.commit()
    db.refresh(wo)
    return wo


@router.post("/work-orders/{wo_id}/approve", response_model=WorkOrderRead)
def approve_work_order(wo_id: str,
                       user: models.User = Depends(require_role("approver")),
                       db: Session = Depends(get_db)):
    """Engineer/approver sign-off — gated by role and recorded in the audit log."""
    wo = db.get(models.Intervention, wo_id)
    if wo is None or wo.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Work order not found")
    wo.approval_status = "approved"
    wo.approved_by = user.id
    wo.approved_at = dt.datetime.now(dt.timezone.utc)
    audit.record(db, user, "work_order", wo.id, "approve", {})
    db.commit()
    db.refresh(wo)
    return wo
