"""
Cost model — transparent unit-rate estimating for defect repairs
================================================================

A quantity-surveying style model, not a black box:

    expected = (quantity x unit rate x adjustment factors)
               + fixed allowances + setup + mobilisation
    band     = expected +/- (12% + 30% x (1 - completeness))

* The repair METHOD per defect type follows the same AASHTO Ch16 /
  Austroads protocols the Defect Detail page prescribes.
* QUANTITY is read from the defect's measurements when present
  (ingested defects) or parsed from the survey evidence text
  (e.g. "length 2.4m", "area 112 cm2"); otherwise a documented
  typical quantity is assumed and the estimate is flagged.
* RATES are indicative Australian figures, deliberately conservative
  and clearly labelled as defaults — calibrate them against your
  maintenance contract or a current Rawlinsons before relying on
  absolute values. Relativities (what is expensive vs cheap) are the
  robust part.
* MOBILISATION reflects that nothing in a live road tunnel is cheap:
  night possession, traffic management and an EWP are priced per
  job, which also acts as the minimum-job floor.
* The CONTINGENCY BAND widens as diagnostic completeness drops —
  weak evidence means uncertain scope, and the band says so.
* Special cases follow the engineering rules already in the app:
  an ACTIVE crack is costed as monitoring + root-cause investigation
  (repair deferred — rebonding an active crack fails); a leaking
  joint with a GPR-detected VOID gets a formation-grouting line
  before surface sealing; S-3/S-4 spalls carry the structural
  assessment / coupler reinstatement allowances that AASHTO §16.4.3
  triggers.

Every figure the model produces is decomposed into labelled lines so
the Defect Detail page can show the full build-up.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

MOBILISATION_AUD = 6500.0   # night possession + traffic mgmt + EWP, per job
ROUND_TO = 100.0

# Base work items per defect type. Rates are indicative AUD defaults.
RATE_TABLE: Dict[str, Dict[str, Any]] = {
    "Cracks": dict(
        method="Pressure epoxy injection (AASHTO Ch16 §16.5 / AS 3600)",
        unit="m of crack", rate=450.0, default_qty=2.5, min_qty=1.0,
        setup=2500.0),
    "LeakingJoints": dict(
        method="Polyurethane grout injection at joint (AASHTO Ch16 §16.3.2)",
        unit="m of joint", rate=650.0, default_qty=3.0, min_qty=2.0,
        setup=3500.0),
    "ConstructionJointDefect": dict(
        method="Rake out and reseal construction joint (Austroads Pt 5)",
        unit="m of joint", rate=600.0, default_qty=3.0, min_qty=2.0,
        setup=3000.0),
    "Spalls": dict(
        method="Break out, treat reinforcement, polymer-modified "
               "reinstatement (AASHTO Ch16 §16.4)",
        unit="m²", rate=1800.0, default_qty=0.25, min_qty=0.25,
        setup=3000.0),
    "Delaminations": dict(
        method="Acoustic sounding, removal, reinstatement per spall "
               "protocol (AASHTO Ch16 §16.6)",
        unit="m²", rate=2200.0, default_qty=0.5, min_qty=0.5,
        setup=3000.0),
    "Delamination": dict(_alias="Delaminations"),
    "RebarCorrosion": dict(
        method="Expose, abrasive-clean to SA 2½, zinc-rich primer, "
               "reinstate cover (AS/NZS 2312)",
        unit="m²", rate=2400.0, default_qty=0.3, min_qty=0.3,
        setup=3500.0),
    "Efflorescence": dict(
        method="Mechanical removal and moisture-pathway sealing "
               "(AASHTO Ch16 §16.5)",
        unit="m²", rate=180.0, default_qty=2.0, min_qty=1.0,
        setup=1500.0),
    "Staining": dict(
        method="Clean staining, identify and seal moisture source "
               "(AASHTO Ch16 §16.5)",
        unit="m²", rate=160.0, default_qty=2.0, min_qty=1.0,
        setup=1500.0),
    "Honeycombing": dict(
        method="Cut out honeycombed zone and reinstate with repair "
               "mortar (AS 5100.5)",
        unit="m²", rate=1600.0, default_qty=0.4, min_qty=0.3,
        setup=2500.0),
}

# Structural allowances triggered by spall/corrosion severity grade
# (AASHTO §16.4.3: S-3 requires structural assessment; S-4 may require
# segment replacement design).
SPALL_STRUCTURAL_ALLOWANCE = {"S-2": 4000.0, "S-3": 20000.0, "S-4": 35000.0}

# Severity multipliers on the work item
SEVERITY_FACTOR = {
    "S-1": 1.0, "S-2": 1.3, "S-3": 1.8, "S-4": 2.5,
    "low": 1.0, "medium": 1.25, "high": 1.6,
}

ENGINEER_REVIEW_ALLOWANCE = 5000.0  # Unclassified defects

# Active-crack pathway (AASHTO Ch16 §16.5: do not rebond)
CRACK_MONITORING_ALLOWANCE = 4200.0     # 90-day gauge/LVDT monitoring
ROOT_CAUSE_INVESTIGATION = 3800.0       # settlement/ground-movement study
VOID_GROUTING_ALLOWANCE = 6000.0        # formation grouting behind lining


def _evidence_text(defect: Dict[str, Any]) -> str:
    """All searchable evidence text for one defect, lowercased."""
    parts = [
        defect.get("description", ""),
        defect.get("threshold_triggered", ""),
        defect.get("indicators_summary", ""),
    ]
    for ev in (defect.get("modality_evidence") or {}).values():
        if isinstance(ev, dict) and ev.get("finding"):
            parts.append(str(ev["finding"]))
    return " ".join(p for p in parts if p).lower()


def _extract_quantity(defect: Dict[str, Any], spec: Dict[str, Any],
                      text: str) -> Tuple[float, bool]:
    """(quantity in the work item's unit, was_assumed)."""
    m = defect.get("measurements") or {}
    unit = spec["unit"]

    if unit.startswith("m of"):  # linear: crack/joint metres
        match = re.search(r"length\s+(\d+(?:\.\d+)?)\s*m", text)
        if match:
            return max(float(match.group(1)), spec["min_qty"]), False
        match = re.search(r"(\d+(?:\.\d+)?)\s*m\s+trail", text)
        if match:
            return max(float(match.group(1)), spec["min_qty"]), False
        return spec["default_qty"], True

    # area-based: m²
    area_cm2 = m.get("area_cm2")
    if not area_cm2:
        match = re.search(r"(?:area|extent)\s+(\d+(?:\.\d+)?)\s*cm", text)
        if match:
            area_cm2 = float(match.group(1))
    if area_cm2:
        return max(float(area_cm2) / 10000.0, spec["min_qty"]), False
    return spec["default_qty"], True


def _severity_factor(defect: Dict[str, Any]) -> Tuple[float, str]:
    sev = str(defect.get("severity") or "").strip()
    if sev in SEVERITY_FACTOR:
        return SEVERITY_FACTOR[sev], sev
    key = sev.lower()
    if key in SEVERITY_FACTOR:
        return SEVERITY_FACTOR[key], sev or "unrated"
    return 1.0, sev or "unrated"


def _round(x: float) -> float:
    return round(x / ROUND_TO) * ROUND_TO


def estimate_defect_cost(defect: Dict[str, Any]) -> Dict[str, Any]:
    """
    Estimate one defect's repair cost. Returns a dict with the expected
    value, the low/high contingency band, and every labelled line that
    builds the figure (for display on Defect Detail).
    """
    defect_type = (defect.get("defect_type") or "Unclassified").strip()
    text = _evidence_text(defect)
    completeness = float(defect.get("completeness_score") or 0.5)
    band_pct = 0.12 + 0.30 * (1.0 - max(0.0, min(1.0, completeness)))

    lines: List[Tuple[str, float]] = []
    factors: List[Tuple[str, float]] = []
    assumptions: List[str] = [
        "Rates are indicative Australian defaults — calibrate against "
        "the maintenance contract before relying on absolute values.",
        "Each defect is priced as a standalone night possession; "
        "batching several repairs into one possession shares the "
        "mobilisation cost and lowers the per-defect figure.",
    ]

    spec = RATE_TABLE.get(defect_type)
    if spec and "_alias" in spec:
        spec = RATE_TABLE[spec["_alias"]]

    quantity, unit = 0.0, ""
    quantity_assumed = False

    if spec is None:
        # Unknown type: engineer-review allowance, no rate line
        method = "Engineer-led inspection and classification"
        lines.append(("Engineer review allowance (unclassified defect)",
                      ENGINEER_REVIEW_ALLOWANCE))
        assumptions.append("Defect type not in the rate table — flat "
                           "review allowance applied.")
    elif defect_type == "Cracks" and ("active" in text
                                      or "do not rebond" in text):
        # AASHTO §16.5: active cracks are monitored, not rebonded
        method = ("Monitor active crack, investigate root cause — "
                  "repair deferred (AASHTO Ch16 §16.5)")
        lines.append(("Crack monitoring, 90 days (gauges/LVDT)",
                      CRACK_MONITORING_ALLOWANCE))
        lines.append(("Root-cause investigation (settlement / ground "
                      "movement)", ROOT_CAUSE_INVESTIGATION))
        lines.append(("Site setup and preparation", spec["setup"]))
        assumptions.append("Active crack: structural repair cost is "
                           "EXCLUDED until movement is confirmed dormant "
                           "and the cause addressed.")
    else:
        method = spec["method"]
        quantity, quantity_assumed = _extract_quantity(defect, spec, text)
        unit = spec["unit"]
        sev_factor, sev_label = _severity_factor(defect)
        if sev_factor != 1.0:
            factors.append((f"Severity {sev_label}", sev_factor))

        # Active-water factor for injection/sealing work
        if "gushing" in text or "gs moisture" in text or "flowing" in text:
            factors.append(("Active water (GS/F) — hydrophilic grout, "
                            "repeat passes", 1.5))
        elif "active leak" in text or " m moisture" in text:
            factors.append(("Damp/seeping (M) — moisture-tolerant "
                            "materials", 1.2))

        # Crown access factor
        if "crown" in str(defect.get("position", "")).lower():
            factors.append(("Crown access (EWP working at apex)", 1.15))

        work = quantity * spec["rate"]
        for _, f in factors:
            work *= f
        lines.append((
            f"{quantity:g} {unit} × ${spec['rate']:,.0f}"
            + "".join(f" × {f:g}" for _, f in factors),
            work,
        ))
        lines.append(("Site setup and preparation", spec["setup"]))

        if quantity_assumed:
            assumptions.append(
                f"No measured extent on file — typical quantity "
                f"({spec['default_qty']:g} {unit}) assumed.")

        # Structural allowance for graded spalls / corrosion
        if defect_type in ("Spalls", "RebarCorrosion"):
            allowance = SPALL_STRUCTURAL_ALLOWANCE.get(
                str(defect.get("severity", "")).strip())
            if allowance:
                lines.append((
                    f"Structural allowance for {defect.get('severity')} "
                    f"(assessment, couplers — AASHTO §16.4.3)", allowance))

        # Void behind lining → formation grouting first. Negative
        # lookbehind so "no void (GPR)" does NOT trigger the line.
        if (re.search(r"(?<!no )\bvoid\b", text)
                and defect_type in ("LeakingJoints",
                                    "ConstructionJointDefect")):
            lines.append(("Formation grouting through GPR-detected void",
                          VOID_GROUTING_ALLOWANCE))

    lines.append(("Mobilisation: night possession, traffic management, "
                  "EWP", MOBILISATION_AUD))

    expected = _round(sum(amount for _, amount in lines))
    low = _round(expected * (1 - band_pct))
    high = _round(expected * (1 + band_pct))

    recorded = float(defect.get("estimated_cost_aud") or 0)
    within_band = (low <= recorded <= high) if recorded else None

    return {
        "ok": True,
        "method": method,
        "lines": lines,
        "factors": factors,
        "quantity": quantity,
        "unit": unit,
        "quantity_assumed": quantity_assumed,
        "expected": expected,
        "low": low,
        "high": high,
        "band_pct": band_pct,
        "completeness": completeness,
        "assumptions": assumptions,
        "recorded": recorded or None,
        "within_band": within_band,
    }


def effective_cost(defect: Dict[str, Any]) -> Tuple[float, str]:
    """
    The cost figure the dashboards should use: the engineer-recorded
    estimate when one exists, otherwise the model's expected value.
    Returns (amount_aud, basis) with basis 'engineer' or 'modelled'.
    """
    recorded = float(defect.get("estimated_cost_aud") or 0)
    if recorded:
        return recorded, "engineer"
    return estimate_defect_cost(defect)["expected"], "modelled"
