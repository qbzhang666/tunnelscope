"""Tunnels — CRUD (org-scoped) + IFC export via the reused utils/."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import domain, models
from ..auth import get_current_user, require_role
from ..db import get_db
from ..schemas import TunnelCreate, TunnelRead

router = APIRouter(prefix="/tunnels", tags=["tunnels"])


@router.post("", response_model=TunnelRead, status_code=201)
def create_tunnel(body: TunnelCreate,
                  user: models.User = Depends(require_role("inspector")),
                  db: Session = Depends(get_db)):
    rings = body.rings_total or (int(body.length_m / body.ring_length_m)
                                 if body.ring_length_m else 0)
    tunnel = models.Tunnel(org_id=user.org_id, label=body.label,
                           alignment=body.alignment, length_m=body.length_m,
                           ring_length_m=body.ring_length_m, rings_total=rings,
                           max_depth_m=body.max_depth_m)
    db.add(tunnel)
    db.commit()
    db.refresh(tunnel)
    return tunnel


@router.get("", response_model=list[TunnelRead])
def list_tunnels(user: models.User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return db.scalars(select(models.Tunnel)
                      .where(models.Tunnel.org_id == user.org_id)).all()


def _get_tunnel(db: Session, user: models.User, tunnel_id: str) -> models.Tunnel:
    tunnel = db.get(models.Tunnel, tunnel_id)
    if tunnel is None or tunnel.org_id != user.org_id:   # org isolation
        raise HTTPException(status_code=404, detail="Tunnel not found")
    return tunnel


@router.get("/{tunnel_id}", response_model=TunnelRead)
def get_tunnel(tunnel_id: str,
               user: models.User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    return _get_tunnel(db, user, tunnel_id)


@router.get("/{tunnel_id}/ifc")
def export_ifc(tunnel_id: str,
               user: models.User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """Build an IFC4 model of the tunnel + its defects (reuses utils.ifc_export)."""
    tunnel = _get_tunnel(db, user, tunnel_id)
    defects = db.scalars(select(models.Defect)
                         .where(models.Defect.tunnel_id == tunnel_id)).all()
    ifc_text = domain.export_ifc(tunnel, defects)
    return Response(content=ifc_text, media_type="application/x-step",
                    headers={"Content-Disposition":
                             f'attachment; filename="{tunnel.label}.ifc"'})
