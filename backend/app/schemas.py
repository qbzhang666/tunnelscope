"""Pydantic v2 request/response models for the implemented routers."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---- auth ----
class DevTokenRequest(BaseModel):
    email: str
    role: str = "viewer"
    org_name: str = "Demo Org"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    org_id: str


# ---- tunnels ----
class TunnelCreate(BaseModel):
    label: str
    alignment: list = Field(default_factory=list)
    length_m: float = 0.0
    ring_length_m: float = 1.6
    rings_total: int = 0
    max_depth_m: Optional[float] = None


class TunnelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    label: str
    length_m: float
    ring_length_m: float
    rings_total: int
    alignment: list


# ---- defects ----
class DefectCreate(BaseModel):
    tunnel_id: str
    defect_type: str = "Unclassified"
    ring_id: Optional[int] = None
    chainage_m: float = 0.0
    position: Optional[str] = None
    severity: Optional[str] = None
    priority: str = "MEDIUM"
    completeness_score: float = 0.5
    measurements: dict = Field(default_factory=dict)
    description: str = ""
    discovered_on: Optional[str] = None
    source: str = "manual"
    estimated_cost_aud: Optional[float] = None


class DefectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tunnel_id: str
    defect_type: str
    ring_id: Optional[int]
    chainage_m: float
    position: Optional[str]
    severity: Optional[str]
    priority: str
    status: str
    completeness_score: float
    measurements: dict
    description: str
    estimated_cost_aud: Optional[float]


# ---- interventions / work orders ----
class WorkOrderCreate(BaseModel):
    steps: list[dict] = Field(default_factory=list)
    deadline_days: Optional[int] = None


class WorkOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    defect_id: str
    steps: list
    deadline_days: Optional[int]
    approval_status: str
    approved_by: Optional[str]
