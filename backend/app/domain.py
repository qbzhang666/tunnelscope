"""
Domain bridge — reuse the Streamlit app's `utils/` from the API.

The whole point of the lean migration: the engineering logic already
exists as plain Python functions that operate on dicts. We convert ORM
rows to those dicts and call the existing code unchanged.

  * cost build-up  -> utils.cost_model.estimate_defect_cost / effective_cost
  * IFC export     -> utils.ifc_export.build_ifc
  * PDF report     -> utils.report.generate_report   (heavy; lazy-imported)

Heavy/UI-coupled modules are imported lazily inside each function so the
API boots fast with only the core deps. (A worthwhile production refactor
is to lift the pure helpers — e.g. PRIORITY_COLOURS, position_to_angle_deg
— out of the folium/plotly-coupled modules so the backend doesn't drag
those UI libraries.)
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

from .config import settings


def _ensure_utils_on_path() -> None:
    """Put the Streamlit repo root (which contains utils/) on sys.path."""
    root = settings.repo_root or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)


def defect_to_dict(defect, observations: List | None = None) -> Dict[str, Any]:
    """Map a Defect ORM row to the plain dict the utils/ functions expect."""
    modality_evidence = {}
    for ob in (observations or getattr(defect, "observations", []) or []):
        modality_evidence[ob.modality] = {
            "status": "Measured", "finding": ob.finding,
            "fmea_level": ob.fmea_level, "confidence": ob.confidence,
        }
    return {
        "defect_id": defect.id,
        "defect_type": defect.defect_type,
        "ring_id": defect.ring_id,
        "chainage_m": defect.chainage_m,
        "position": defect.position,
        "severity": defect.severity,
        "priority": defect.priority,
        "status": defect.status,
        "completeness_score": defect.completeness_score,
        "measurements": defect.measurements or {},
        "description": defect.description,
        "discovered_on": defect.discovered_on,
        "estimated_cost_aud": defect.estimated_cost_aud,
        "modality_evidence": modality_evidence,
    }


def tunnel_to_dict(tunnel) -> Dict[str, Any]:
    return {
        "tunnel_id": tunnel.id,
        "label": tunnel.label,
        "length_m": tunnel.length_m,
        "ring_length_m": tunnel.ring_length_m,
        "rings_total": tunnel.rings_total,
        "alignment": tunnel.alignment,
    }


# -----------------------------------------------------------------------------
# Cost model (light — utils.cost_model imports only stdlib)
# -----------------------------------------------------------------------------
def estimate_cost(defect) -> Dict[str, Any]:
    _ensure_utils_on_path()
    from utils.cost_model import estimate_defect_cost
    return estimate_defect_cost(defect_to_dict(defect))


def effective_cost(defect):
    _ensure_utils_on_path()
    from utils.cost_model import effective_cost as _ec
    return _ec(defect_to_dict(defect))


# -----------------------------------------------------------------------------
# IFC export (utils.ifc_export -> bim3d/gis pull numpy/plotly/folium)
# -----------------------------------------------------------------------------
def export_ifc(tunnel, defects, bim_record=None) -> str:
    _ensure_utils_on_path()
    from utils.ifc_export import build_ifc
    return build_ifc(
        tunnel_to_dict(tunnel), bim_record,
        [defect_to_dict(d) for d in defects],
    )


# -----------------------------------------------------------------------------
# PDF report (heavy: matplotlib + a LaTeX engine). Lazy + optional.
# -----------------------------------------------------------------------------
def generate_report(tunnel, defects, bim_record=None) -> Dict[str, Any]:
    _ensure_utils_on_path()
    from utils.report import generate_report as _gen
    return _gen(tunnel_to_dict(tunnel), bim_record,
                [defect_to_dict(d) for d in defects], include_case_files=True)
