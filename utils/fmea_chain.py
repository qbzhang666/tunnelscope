"""
FMEA chain traversal and diagnostic completeness logic.

Implements the chain-level complementarity framework described in the
paper: each modality enters the FMEA chain at a specific level, and
diagnostic completeness is the fraction of levels with evidence.
"""

from typing import Dict, List, Any, Tuple


# -----------------------------------------------------------------------------
# Modality to FMEA level mapping
# -----------------------------------------------------------------------------
# Which FMEA levels each modality CAN provide evidence at.
# Keyed as: modality -> set of levels it supports
MODALITY_LEVELS: Dict[str, List[str]] = {
    "RGB":     ["DefectCondition", "MeasuredIndicator_qualitative"],
    "RGBD":    ["MeasuredIndicator_quantitative"],
    "Thermal": ["DefectCondition_subsurface", "PotentialCause"],
    "GPR":     ["MeasuredIndicator_quantitative", "PotentialCause", "Structure"],
}

# Modality detection limitations — what each CANNOT detect
MODALITY_LIMITATIONS: Dict[str, List[str]] = {
    "RGB":     ["subsurface_delamination", "rebar_condition", "voids"],
    "RGBD":    ["internal_lining_condition", "moisture_source"],
    "Thermal": ["crack_depth", "rebar_section_loss", "void_geometry"],
    "GPR":     ["surface_defect_classification", "active_flow_rate"],
}

# Which FMEA levels are required to consider the chain complete
# for a given defect type
REQUIRED_LEVELS_BY_DEFECT = {
    "LeakingJoints":   ["DefectCondition", "MeasuredIndicator_qualitative",
                        "PotentialCause", "Structure"],
    "Spalls":          ["DefectCondition", "MeasuredIndicator_quantitative",
                        "PotentialCause", "Structure"],
    "Cracks":          ["DefectCondition", "MeasuredIndicator_quantitative",
                        "PotentialCause"],
    "Delaminations":   ["DefectCondition_subsurface",
                        "MeasuredIndicator_quantitative", "Structure"],
}


def compute_completeness(
    defect_type: str,
    available_modalities: List[str],
) -> Tuple[float, List[str], List[str]]:
    """
    Compute diagnostic completeness for a defect.

    Returns:
        completeness_score: 0.0 to 1.0
        levels_covered: list of FMEA chain levels with evidence
        levels_missing: list of required levels that lack evidence
    """
    required = set(REQUIRED_LEVELS_BY_DEFECT.get(defect_type, [
        "DefectCondition", "MeasuredIndicator_quantitative",
        "PotentialCause", "Structure",
    ]))

    covered = set()
    for modality in available_modalities:
        for level in MODALITY_LEVELS.get(modality, []):
            if level in required or _level_matches_any(level, required):
                covered.add(level)

    # Normalise — collapse qualitative/quantitative variants
    covered_normalised = {_normalise_level(l) for l in covered}
    required_normalised = {_normalise_level(l) for l in required}

    covered_count = len(covered_normalised & required_normalised)
    required_count = len(required_normalised)

    if required_count == 0:
        return 1.0, [], []

    score = covered_count / required_count
    covered_list = sorted(covered_normalised & required_normalised)
    missing_list = sorted(required_normalised - covered_normalised)

    return score, covered_list, missing_list


def _level_matches_any(level: str, required_set: set) -> bool:
    """Handle variant level names (e.g. DefectCondition vs DefectCondition_subsurface)."""
    base = _normalise_level(level)
    return base in {_normalise_level(r) for r in required_set}


def _normalise_level(level: str) -> str:
    """Strip the _qualitative/_quantitative/_subsurface suffixes."""
    for suffix in ["_qualitative", "_quantitative", "_subsurface"]:
        if level.endswith(suffix):
            return level[: -len(suffix)]
    return level


def recommend_missing_modality(
    defect_type: str,
    available_modalities: List[str],
) -> List[Dict[str, str]]:
    """
    Recommend which additional modality to deploy to fill FMEA chain gaps.

    Returns list of recommendations with modality name, level it would
    populate, and rationale.
    """
    score, _, missing = compute_completeness(defect_type, available_modalities)

    if score >= 1.0:
        return []

    recommendations = []

    # Check limitations — don't recommend a modality that cannot detect
    # the relevant defect type
    defect_key = defect_type.lower()

    for missing_level in missing:
        candidates = []
        for modality, levels in MODALITY_LEVELS.items():
            if modality in available_modalities:
                continue
            if any(_normalise_level(l) == missing_level for l in levels):
                # Verify this modality can detect this defect type
                limitations = MODALITY_LIMITATIONS.get(modality, [])
                if not any(lim in defect_key for lim in limitations):
                    candidates.append(modality)

        for modality in candidates:
            recommendations.append({
                "modality": modality,
                "level": missing_level,
                "rationale": f"{modality} provides evidence at the "
                             f"{missing_level} level, which is currently "
                             f"missing for this defect.",
            })

    return recommendations


def decision_pathway(completeness_score: float) -> Dict[str, str]:
    """
    Return the decision pathway for a given completeness score.

    Implements the threshold gating described in the paper:
        >= 0.75 → automated decision
        0.5 - 0.75 → provisional with flag
        < 0.5 → survey request only
    """
    if completeness_score >= 0.75:
        return {
            "pathway": "AUTOMATED",
            "confidence": "HIGH",
            "action": "Generate work order with full intervention prescription.",
            "engineer_approval": "Required before execution.",
        }
    elif completeness_score >= 0.5:
        return {
            "pathway": "PROVISIONAL",
            "confidence": "MEDIUM",
            "action": "Generate work order with caveat. Flag missing evidence.",
            "engineer_approval": "Required. Targeted survey recommended.",
        }
    else:
        return {
            "pathway": "SURVEY_REQUEST",
            "confidence": "LOW",
            "action": "Defer intervention. Request additional modality deployment.",
            "engineer_approval": "Not requested yet. Complete survey first.",
        }
