"""
SQLAlchemy 2.0 schema — the "real version" data model.

Portable across SQLite (zero-setup dev) and PostgreSQL (production). A
few production-only choices are noted inline:

  * Tunnel.alignment is JSON here; in Postgres it becomes
    geometry(LineString, 4326) via GeoAlchemy2 + PostGIS.
  * Tenant isolation is enforced in the query layer (every read filters
    by org_id). In Postgres, add Row-Level Security as defence in depth.

Every tenant-scoped row carries org_id from day one, even while the
pilot is single-tenant — retrofitting it later is painful.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, Float, ForeignKey, JSON, DateTime, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now())


# -----------------------------------------------------------------------------
# Tenancy & identity
# -----------------------------------------------------------------------------
class Organization(Base, TimestampMixin):
    __tablename__ = "organization"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    region: Mapped[str] = mapped_column(String(40), default="AU")


class User(Base, TimestampMixin):
    __tablename__ = "app_user"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organization.id"))
    email: Mapped[str] = mapped_column(String(255))
    # viewer | inspector | engineer | approver | admin
    role: Mapped[str] = mapped_column(String(20), default="viewer")


# -----------------------------------------------------------------------------
# Asset (tunnel) + as-built / geology context
# -----------------------------------------------------------------------------
class Tunnel(Base, TimestampMixin):
    __tablename__ = "tunnel"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organization.id"), index=True)
    label: Mapped[str] = mapped_column(String(200))
    # Production: geometry(LineString, 4326). Here: [[lat, lon], ...].
    alignment: Mapped[list] = mapped_column(JSON, default=list)
    length_m: Mapped[float] = mapped_column(Float, default=0.0)
    ring_length_m: Mapped[float] = mapped_column(Float, default=1.6)
    rings_total: Mapped[int] = mapped_column(Integer, default=0)
    max_depth_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    defects: Mapped[list["Defect"]] = relationship(
        back_populates="tunnel", cascade="all, delete-orphan")


class TunnelSegment(Base, TimestampMixin):
    """BIM as-built record for a construction segment of a tunnel."""
    __tablename__ = "tunnel_segment"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organization.id"), index=True)
    tunnel_id: Mapped[str] = mapped_column(ForeignKey("tunnel.id"))
    segment_id: Mapped[str] = mapped_column(String(60))
    ring_range: Mapped[list] = mapped_column(JSON, default=list)        # [lo, hi]
    concrete_mix: Mapped[dict] = mapped_column(JSON, default=dict)
    reinforcement: Mapped[dict] = mapped_column(JSON, default=dict)
    contractor: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    attrs: Mapped[dict] = mapped_column(JSON, default=dict)             # diameter, joint type...


class GeologyZone(Base, TimestampMixin):
    __tablename__ = "geology_zone"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organization.id"), index=True)
    tunnel_id: Mapped[str] = mapped_column(ForeignKey("tunnel.id"))
    zone_id: Mapped[str] = mapped_column(String(60))
    chainage_range: Mapped[list] = mapped_column(JSON, default=list)
    stratigraphy: Mapped[dict] = mapped_column(JSON, default=dict)
    hazards: Mapped[list] = mapped_column(JSON, default=list)


# -----------------------------------------------------------------------------
# Inspection campaigns & defects (the core)
# -----------------------------------------------------------------------------
class Inspection(Base, TimestampMixin):
    __tablename__ = "inspection"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organization.id"), index=True)
    tunnel_id: Mapped[str] = mapped_column(ForeignKey("tunnel.id"))
    campaign_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    surveyor: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    modalities: Mapped[list] = mapped_column(JSON, default=list)


class Defect(Base, TimestampMixin):
    __tablename__ = "defect"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organization.id"), index=True)
    tunnel_id: Mapped[str] = mapped_column(ForeignKey("tunnel.id"), index=True)
    inspection_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("inspection.id"), nullable=True)

    defect_type: Mapped[str] = mapped_column(String(60), default="Unclassified")
    ring_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chainage_m: Mapped[float] = mapped_column(Float, default=0.0)
    position: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    priority: Mapped[str] = mapped_column(String(10), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(20), default="Active")
    completeness_score: Mapped[float] = mapped_column(Float, default=0.5)
    measurements: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(Text, default="")
    discovered_on: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual|image|report|cv
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_cost_aud: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    tunnel: Mapped["Tunnel"] = relationship(back_populates="defects")
    observations: Mapped[list["ModalityObservation"]] = relationship(
        back_populates="defect", cascade="all, delete-orphan")
    interventions: Mapped[list["Intervention"]] = relationship(
        back_populates="defect", cascade="all, delete-orphan")


class ModalityObservation(Base, TimestampMixin):
    __tablename__ = "modality_observation"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    defect_id: Mapped[str] = mapped_column(ForeignKey("defect.id"), index=True)
    modality: Mapped[str] = mapped_column(String(20))   # RGB|RGBD|Thermal|GPR
    finding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fmea_level: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    artifact_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("artifact.id"), nullable=True)

    defect: Mapped["Defect"] = relationship(back_populates="observations")


# -----------------------------------------------------------------------------
# Interventions / work orders (the engineer sign-off + audit surface)
# -----------------------------------------------------------------------------
class Intervention(Base, TimestampMixin):
    __tablename__ = "intervention"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organization.id"), index=True)
    defect_id: Mapped[str] = mapped_column(ForeignKey("defect.id"), index=True)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    deadline_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approval_status: Mapped[str] = mapped_column(String(20), default="pending")
    approved_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("app_user.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)

    defect: Mapped["Defect"] = relationship(back_populates="interventions")


class CostEstimate(Base, TimestampMixin):
    __tablename__ = "cost_estimate"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    defect_id: Mapped[str] = mapped_column(ForeignKey("defect.id"), index=True)
    expected: Mapped[float] = mapped_column(Float, default=0.0)
    low: Mapped[float] = mapped_column(Float, default=0.0)
    high: Mapped[float] = mapped_column(Float, default=0.0)
    basis: Mapped[str] = mapped_column(String(20), default="modelled")
    lines: Mapped[list] = mapped_column(JSON, default=list)


# -----------------------------------------------------------------------------
# Artifacts (object-storage pointers) + audit
# -----------------------------------------------------------------------------
class Artifact(Base, TimestampMixin):
    __tablename__ = "artifact"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organization.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))   # image|report|pdf|ifc|cobie
    storage_key: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class AuditLog(Base):
    """Every defect change, approval, and export — safety/liability record."""
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organization.id"), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("app_user.id"), nullable=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
