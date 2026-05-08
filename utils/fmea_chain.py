"""
FMEA chain reasoning utilities
==============================

Core logic for evaluating evidence completeness and recommending
modality enhancements. Used by Defect Register, Defect Detail,
and Ingest pages.

DESIGN NOTE — REVISED
---------------------
This module no longer *blocks* interventions when evidence is sparse.
A single-modality input (e.g. one RGB photo, or a text inspection
report) is a legitimate operator workflow. The completeness score
now drives a *confidence tier* label, not a permission gate.

    completeness >= 0.75   -> HIGH confidence
    0.5 <= completeness    -> MEDIUM confidence
    completeness < 0.5     -> LOW confidence (still actionable)

Interventions are always prescribed when the FMEA chain has at least
a defect type and a component. Confidence tiering tells the engineer
how much to trust the recommendation, not whether they're allowed
to see it.
"""

from typing import Dict, List, Tuple


# -----------------------------------------------------------------------------
# Modality framework (paper Section 3.6)
# -----------------------------------------------------------------------------
# Which FMEA chain levels each modality can populate.
# Levels follow the seven-step chain collapsed into the four observable
# evidence levels:
#     defect       — what is wrong (qualitative)
#     indicator    — how bad (quantitative dimensions)
#     cause        — why it is happening (subsurface or thermal)
#     subsurface   — what is inside the lining
MODALITY_LEVELS: Dict[str, List[str]] = {
    "RGB":     ["defect_qualitative"],
    "RGBD":    ["defect_qualitative", "indicator_quantitative"],
    "Thermal": ["cause_qualitative", "indicator_quantitative"],
    "GPR":     ["cause_subsurface", "indicator_quantitative"],
    # Text/inspection report contributes at the defect level via the
    # inspector's classification, sometimes at indicator level if
    # measurements are recorded.
    "InspectionReport": ["defect_qualitative", "indicator_quantitative"],
}

# Defect types each modality genuinely cannot detect — used to suppress
# nonsensical "deploy modality X" recommendations.
MODALITY_LIMITATIONS: Dict[str, List[str]] = {
    "RGB":     ["void", "rebar", "subsurface"],
    "RGBD":    ["void", "rebar", "subsurface"],
    "Thermal": ["rebar_corrosion_internal"],
    "GPR":     ["surface_staining", "efflorescence"],
    "InspectionReport": [],
}

# All four evidence levels we want covered for a "complete" FMEA chain.
ALL_LEVELS = [
    "defect_qualitative",
    "indicator_quantitative",
    "cause_qualitative",
    "cause_subsurface",
]


def _normalise_level(level: str) -> str:
    """Strip suffixes so 'defect_qualitative' and 'defect' compare equal."""
    for suffix in ["_qualitative", "_quantitative", "_subsurface"]:
        if level.endswith(suffix):
            return level[: -len(suffix)]
    return level


# -----------------------------------------------------------------------------
# Completeness scoring
# -----------------------------------------------------------------------------
def compute_completeness(
    defect_type: str,
    available_modalities: List[str],
) -> Tuple[float, List[str], List[str]]:
    """
    Score how completely the available modalities cover the FMEA chain
    for this defect type.

    Returns
    -------
    score : float in [0, 1]
        Fraction of the four evidence levels that are covered.
    covered : list of level names that ARE covered.
    missing : list of level names that are NOT covered.

    Note
    ----
    A score of 0 does NOT mean "do nothing." It means the recommendation
    will be tagged LOW confidence. The page-level UI handles that
    framing — this function is purely descriptive.
    """
    covered_set = set()
    for modality in available_modalities:
        for level in MODALITY_LEVELS.get(modality, []):
            covered_set.add(level)

    covered = [lvl for lvl in ALL_LEVELS if lvl in covered_set]
    missing = [lvl for lvl in ALL_LEVELS if lvl not in covered_set]

    score = len(covered) / len(ALL_LEVELS) if ALL_LEVELS else 0.0
    return score, covered, missing


def recommend_missing_modality(
    defect_type: str,
    available_modalities: List[str],
) -> List[Dict[str, str]]:
    """
    Recommend additional modalities that would *enhance* the diagnosis.

    Framed as enhancement, not a prerequisite. Used in the Defect Detail
    page under "Additional surveys could strengthen this assessment".
    """
    score, _, missing = compute_completeness(defect_type, available_modalities)

    if score >= 1.0:
        return []

    recommendations = []
    defect_key = defect_type.lower()

    for missing_level in missing:
        for modality, levels in MODALITY_LEVELS.items():
            if modality in available_modalities:
                continue
            if modality == "InspectionReport":
                # Don't recommend a written report as a "survey to deploy".
                continue
            if any(_normalise_level(l) == _normalise_level(missing_level)
                   for l in levels):
                limitations = MODALITY_LIMITATIONS.get(modality, [])
                if any(lim in defect_key for lim in limitations):
                    continue
                recommendations.append({
                    "modality": modality,
                    "level": missing_level,
                    "rationale": (
                        f"{modality} would add evidence at the "
                        f"{_normalise_level(missing_level)} level, "
                        f"strengthening the diagnosis."
                    ),
                })

    # Deduplicate by modality
    seen = set()
    unique = []
    for rec in recommendations:
        if rec["modality"] in seen:
            continue
        seen.add(rec["modality"])
        unique.append(rec)
    return unique


# -----------------------------------------------------------------------------
# Confidence tier (formerly the decision-pathway gate)
# -----------------------------------------------------------------------------
def confidence_tier(completeness_score: float) -> Dict[str, str]:
    """
    Map a completeness score to a confidence tier label.

    REVISED LOGIC: This no longer blocks intervention output. Every
    tier produces a valid recommendation; the tier label tells the
    engineer how much to trust it and what would strengthen the case.

    Returns a dict with:
        tier     — HIGH / MEDIUM / LOW
        label    — short human label for the badge
        action   — guidance on how to treat the recommendation
        upgrade  — what would lift the tier
    """
    if completeness_score >= 0.75:
        return {
            "tier": "HIGH",
            "label": "High confidence",
            "action": (
                "Recommendation is supported by complementary evidence "
                "across the FMEA chain. Engineer review is still required "
                "before execution, but the diagnostic basis is strong."
            ),
            "upgrade": (
                "No additional surveys required for this decision."
            ),
        }
    elif completeness_score >= 0.5:
        return {
            "tier": "MEDIUM",
            "label": "Medium confidence",
            "action": (
                "Recommendation is defensible but rests on partial "
                "evidence. Proceed with engineer review; a targeted "
                "follow-up survey would strengthen the case."
            ),
            "upgrade": (
                "Adding one more modality would lift this to HIGH "
                "confidence — see the recommendations below."
            ),
        }
    else:
        return {
            "tier": "LOW",
            "label": "Low confidence",
            "action": (
                "Recommendation is based on limited evidence (e.g. a "
                "single image or a text-only report). Engineer judgement "
                "is essential. The recommendation is intended as a "
                "starting point, not a final decision."
            ),
            "upgrade": (
                "Deploying additional modalities would meaningfully "
                "improve diagnostic certainty — see suggestions below."
            ),
        }


# Backward-compatible alias — old code calls decision_pathway()
def decision_pathway(completeness_score: float) -> Dict[str, str]:
    """Deprecated alias. Returns confidence_tier with legacy keys."""
    tier = confidence_tier(completeness_score)
    return {
        "pathway": tier["tier"],
        "confidence": tier["tier"],
        "action": tier["action"],
        "engineer_approval": "Required before execution.",
    }


# -----------------------------------------------------------------------------
# Modality state for the three-state UI matrix
# -----------------------------------------------------------------------------
def modality_state(
    modality: str,
    defect_type: str,
    has_evidence: bool,
) -> str:
    """
    Return one of three states for the modality matrix UI:

        "present"        — evidence collected and used in the chain
        "could_enhance"  — not collected; would add useful evidence
        "not_applicable" — this modality cannot detect this defect type

    Replaces the old binary present/missing logic, which incorrectly
    framed any absence as a deficiency.
    """
    if has_evidence:
        return "present"

    limitations = MODALITY_LIMITATIONS.get(modality, [])
    defect_key = defect_type.lower()
    if any(lim in defect_key for lim in limitations):
        return "not_applicable"

    return "could_enhance"
