"""
Defect Detail — page 2
======================

Shows the full FMEA reasoning chain for a single defect, including:
    - Three-state modality matrix (present / could enhance / not applicable)
    - Confidence tier label (HIGH / MEDIUM / LOW) — never blocks output
    - FMEA chain: Component → Mechanism → Defect → Indicator
                  → Cause → Threshold → Intervention
    - Prescribed intervention with materials, deadline, cost, standards ref
    - Modality enhancement recommendations
    - Work order generation and COBie export

REVISED:
- Selectbox moved to top of page (above title) to fix label cropping.
- Single-modality input is a first-class case — full intervention shown
  with a LOW confidence label rather than a refusal.
- Modality matrix has three states (present / could enhance / not applicable).
"""

import streamlit as st
import json

from utils.ontology_loader import (
    load_ontology, load_defects, get_defect_by_id,
    get_fmea_chain, get_modality_evidence,
)
from utils.fmea_chain import (
    compute_completeness, recommend_missing_modality, confidence_tier,
    modality_state, MODALITY_LEVELS,
)
from utils.styling import apply_custom_css

st.set_page_config(page_title="Defect Detail", layout="wide")
apply_custom_css()

if "graph" not in st.session_state:
    st.session_state.graph = load_ontology()
    st.session_state.defects = load_defects(st.session_state.graph)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _summarise_measurements(defect: dict) -> str:
    """Build a one-line summary of any quantitative measurements on file."""
    m = defect.get("measurements", {})
    parts = []
    if m.get("crack_width_mm"):
        parts.append(f"width {m['crack_width_mm']} mm")
    if m.get("spall_depth_mm"):
        parts.append(f"depth {m['spall_depth_mm']} mm")
    if m.get("area_cm2"):
        parts.append(f"area {m['area_cm2']} cm²")
    if not parts:
        return "Quantitative measurements not yet recorded."
    return "; ".join(parts)


def _default_interventions_for_type(defect_type: str) -> list:
    """
    Fall-back intervention plan keyed on defect type, used when the
    ontology has no explicit prescribed_interventions for the record.
    """
    table = {
        "Cracks": [
            {"step": "Install crack monitoring gauges to determine "
                     "active vs dormant status (minimum 2 readings, "
                     "30 days apart)",
             "rationale": "Active cracks must not be rigidly rebonded.",
             "reference": "AASHTO Ch16 §16.7"},
            {"step": "If dormant: epoxy resin injection per "
                     "AS 3600 / amine-based resin for moist substrate",
             "rationale": "Restores monolithic concrete integrity.",
             "reference": "AASHTO Ch16 Table 16-2"},
            {"step": "If active: investigate root cause; seal with "
                     "flexible chemical grout if leaking",
             "rationale": "Rigid repair will fail if movement continues.",
             "reference": "AASHTO Ch16 §16.7.3"},
        ],
        "Spalls": [
            {"step": "Remove loose and unsound concrete by "
                     "hydro-demolition or controlled chipping",
             "rationale": "Sound substrate is required for repair adhesion.",
             "reference": "AASHTO Ch16 §16.6.2"},
            {"step": "Inspect exposed reinforcement; clean to SA 2½ "
                     "if section loss < 30%, replace if ≥ 30%",
             "rationale": "Threshold for structural-engineer review.",
             "reference": "AASHTO Ch16 Table 16-3"},
            {"step": "Reinstate with polymer-modified mortar or "
                     "shotcrete; cure per manufacturer specification",
             "rationale": "Restores cover and protects rebar.",
             "reference": "AS 5100.5 / AASHTO Ch16"},
        ],
        "LeakingJoints": [
            {"step": "Categorise leakage per Austroads coding "
                     "(M / PM / GS / F / D)",
             "rationale": "Drives grout selection.",
             "reference": "Austroads Guide Part 5"},
            {"step": "Inject hydrophilic polyurethane grout for "
                     "active flow; epoxy for damp-only",
             "rationale": "Hydrophilic PU expands on contact with water.",
             "reference": "AASHTO Ch16 Table 16-2"},
            {"step": "Re-inspect at 30 days; re-treat if leakage recurs",
             "rationale": "Confirms seal integrity.",
             "reference": "Austroads Guide Part 5"},
        ],
        "Efflorescence": [
            {"step": "Mechanically remove deposits by wire brushing "
                     "or low-pressure water blasting",
             "rationale": "Restores surface aesthetics and exposes "
                          "underlying substrate for inspection.",
             "reference": "AASHTO Ch16 §16.5"},
            {"step": "Investigate moisture pathway (likely cause); "
                     "seal upstream source if identified",
             "rationale": "Without sealing, deposits will recur.",
             "reference": "AASHTO Ch16 §16.7"},
        ],
        "RebarCorrosion": [
            {"step": "Quantify section loss by callipers or ultrasonic "
                     "thickness gauge",
             "rationale": "Threshold of 30% triggers structural review.",
             "reference": "AASHTO Ch16 Table 16-3"},
            {"step": "Remove unsound concrete, abrasive-blast rebar "
                     "to SA 2½, apply zinc-rich primer within 4 hours",
             "rationale": "Prevents flash-rust before reinstatement.",
             "reference": "AS/NZS 2312"},
            {"step": "Reinstate cover with polymer-modified mortar; "
                     "consider impressed-current cathodic protection "
                     "for chloride-contaminated environments",
             "rationale": "Long-term mitigation in saline conditions.",
             "reference": "ISO 12696"},
        ],
        "Delamination": [
            {"step": "Acoustic sounding (chain-drag or hammer) to map "
                     "extent of delaminated zones",
             "rationale": "Visual extent typically underestimates "
                          "subsurface extent.",
             "reference": "AASHTO Ch16 §16.6"},
            {"step": "Remove all delaminated material; reinstate per "
                     "Spalls protocol",
             "rationale": "Standard repair sequence.",
             "reference": "AASHTO Ch16 §16.6.2"},
        ],
    }
    if defect_type in table:
        return table[defect_type]
    return [
        {"step": "Engineer-led inspection to confirm defect "
                 "classification and select intervention",
         "rationale": "Defect type does not match a standard protocol "
                      "in the loaded knowledge base.",
         "reference": "Engineer judgement"},
    ]


# -----------------------------------------------------------------------------
# Page header — title FIRST, then selectbox below with breathing room
# -----------------------------------------------------------------------------
st.title("Defect detail")
st.caption(
    "Full FMEA reasoning chain and prescribed intervention for a single "
    "defect. Pick a defect from the dropdown below."
)

defects = st.session_state.defects
defect_ids = [d["defect_id"] for d in defects]

if not defect_ids:
    st.warning(
        "No defects available. Use the **Ingest** page to register one, "
        "or load sample data into the ontology."
    )
    st.stop()

default_id = st.session_state.get("selected_defect_id") or defect_ids[0]

# Add visual breathing room before the selectbox so the label can't be
# clipped by content above (the bug we hit on the first revision).
st.write("")

selected_id = st.selectbox(
    "Select defect",
    options=defect_ids,
    index=defect_ids.index(default_id) if default_id in defect_ids else 0,
    key="defect_detail_selector",
)

defect = next((d for d in defects if d["defect_id"] == selected_id), {})
if not defect:
    st.error(f"Defect {selected_id} not found.")
    st.stop()

st.divider()

# -----------------------------------------------------------------------------
# Header for the selected defect
# -----------------------------------------------------------------------------
st.subheader(f"{defect['defect_id']} — {defect['description']}")
caption_parts = [
    f"Ring {defect['ring_id']}",
    f"Chainage K{defect.get('chainage_m', 0):.0f}m",
    f"{defect.get('position', '—')}",
    f"Discovered {defect.get('discovered_on', 'unknown')}",
]
if defect.get("ingested"):
    caption_parts.append(
        f"📤 ingested from `{defect.get('source_filename', 'upload')}`"
    )
st.caption(" · ".join(caption_parts))

# Compute confidence tier upfront — used in header and throughout
evidence = defect.get("modality_evidence", {})
available_modalities = [m for m in ["RGB", "RGBD", "Thermal", "GPR"]
                        if evidence.get(m)]
score, covered, missing = compute_completeness(
    defect["defect_type"], available_modalities
)
tier = confidence_tier(score)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Defect type", defect["defect_type"])
with col2:
    st.metric("Priority", defect.get("priority", "—"))
with col3:
    st.metric("Confidence", tier["label"])
with col4:
    cost = defect.get("estimated_cost_aud", 0)
    st.metric("Est. cost", f"${cost:,}" if cost else "Pending")

if tier["tier"] == "HIGH":
    st.success(f"**{tier['label']}** — {tier['action']}")
elif tier["tier"] == "MEDIUM":
    st.info(f"**{tier['label']}** — {tier['action']}")
else:
    st.warning(f"**{tier['label']}** — {tier['action']}")

st.divider()

# -----------------------------------------------------------------------------
# Modality evidence matrix — three states
# -----------------------------------------------------------------------------
st.subheader("Evidence sources")
st.caption(
    "What each sensing modality contributes for this defect. "
    "Green = present · Grey = could enhance · Disabled = not applicable to "
    "this defect type."
)

cols = st.columns(4)
for i, modality in enumerate(["RGB", "RGBD", "Thermal", "GPR"]):
    with cols[i]:
        mod_data = evidence.get(modality, {})
        has_evidence = bool(mod_data)
        state = modality_state(modality, defect["defect_type"], has_evidence)

        st.markdown(f"**{modality}**")

        if state == "present":
            status = "✓ " + mod_data.get("status", "Confirmed")
            st.success(status)
            if mod_data.get("finding"):
                st.caption(mod_data["finding"])
            if mod_data.get("fmea_level"):
                st.caption(f"Level: {mod_data['fmea_level']}")

        elif state == "could_enhance":
            st.markdown(":grey[○ Not collected]")
            st.caption("Optional — would add evidence at the "
                       f"{MODALITY_LEVELS.get(modality, ['—'])[0]} level.")

        else:  # not_applicable
            st.markdown(":grey[— Not applicable]")
            st.caption("This modality cannot detect this defect type.")

if evidence.get("InspectionReport") or evidence.get("RGB", {}).get("status") == "Reported by inspector":
    st.markdown("---")
    rep = evidence.get("InspectionReport") or evidence.get("RGB", {})
    st.markdown("**📄 Inspection report** — " + rep.get("status", "Recorded"))
    if rep.get("finding"):
        st.caption(rep["finding"])

# -----------------------------------------------------------------------------
# Evidence breadth & enhancement suggestions
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Evidence breadth")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**FMEA levels covered**")
    if covered:
        for level in covered:
            st.markdown(f"✓ {level.replace('_', ' ')}")
    else:
        st.markdown(":grey[None — relying on a single source.]")
    if missing:
        st.markdown("**Levels not yet covered**")
        for level in missing:
            st.markdown(f":grey[○ {level.replace('_', ' ')}]")

with col2:
    st.markdown(f"**Confidence tier:** {tier['label']}")
    st.caption(tier["upgrade"])

    recommendations = recommend_missing_modality(
        defect["defect_type"], available_modalities
    )
    if recommendations:
        st.markdown("**Recommended enhancements**")
        for rec in recommendations[:3]:
            st.markdown(f"- Deploy **{rec['modality']}** — {rec['rationale']}")
    else:
        st.markdown(":green[No further surveys needed for this decision.]")

# -----------------------------------------------------------------------------
# FMEA reasoning chain
# -----------------------------------------------------------------------------
st.divider()
st.subheader("FMEA reasoning chain")

chain_data = defect.get("fmea_chain", [])
if not chain_data:
    chain_data = [
        {"step": "1. Component",
         "value": f"Concrete lining at Ring {defect['ring_id']}",
         "source": f"COBie.Component.ComponentName = \"Ring_{defect['ring_id']}\""},
        {"step": "2. Failure mechanism",
         "value": defect.get("failure_mechanism", "Not classified"),
         "source": "tun:hasMechanism"},
        {"step": "3. Defect condition",
         "value": defect.get("description", ""),
         "source": f"tun:DefectCondition tun:{defect['defect_type']}"},
        {"step": "4. Indicators",
         "value": defect.get("indicators_summary",
                             _summarise_measurements(defect)),
         "source": "tun:hasIndicator"},
        {"step": "5. Potential cause",
         "value": defect.get("potential_cause", "Inferred from defect type"),
         "source": "tun:hasPotentialCause"},
        {"step": "6. Threshold triggered",
         "value": defect.get("threshold_triggered",
                             "AASHTO Ch16 standard threshold"),
         "source": defect.get("threshold_reference",
                              "AASHTO Manual for Bridge Element Inspection")},
    ]

for step in chain_data:
    with st.container():
        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown(f"**{step['step']}**")
        with col2:
            st.write(step["value"])
            if step.get("source"):
                st.code(step["source"], language=None)

# -----------------------------------------------------------------------------
# Prescribed intervention — ALWAYS shown
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Prescribed intervention")

if tier["tier"] == "LOW":
    st.caption(
        "ℹ️ Recommendation generated from limited evidence. Treat as an "
        "engineer-review starting point. Consider deploying additional "
        "modalities before committing to scheduling."
    )

interventions = defect.get("prescribed_interventions", [])
if not interventions:
    interventions = _default_interventions_for_type(defect["defect_type"])

for i, iv in enumerate(interventions, 1):
    with st.container():
        col1, col2 = st.columns([1, 6])
        with col1:
            st.markdown(f"### {i}")
        with col2:
            st.markdown(f"**{iv['step']}**")
            if iv.get("rationale"):
                st.caption(iv["rationale"])
            if iv.get("reference"):
                st.code(iv["reference"], language=None)

deadline = defect.get("deadline_days")
if deadline:
    st.warning(f"Complete within **{deadline} days** of approval.")

# -----------------------------------------------------------------------------
# Actions
# -----------------------------------------------------------------------------
st.divider()
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("Generate work order", type="primary"):
        st.success("Work order generated. See download below.")
        work_order = {
            "work_order_id": f"WO-{defect['defect_id']}-{defect.get('discovered_on', '')}",
            "defect": defect,
            "confidence_tier": tier,
            "evidence_breadth": {
                "score": score,
                "modalities_present": available_modalities,
                "modalities_missing": [
                    m for m in ["RGB", "RGBD", "Thermal", "GPR"]
                    if m not in available_modalities
                ],
            },
            "approval_status": "PENDING_ENGINEER_REVIEW",
        }
        st.download_button(
            "Download work order (JSON)",
            json.dumps(work_order, indent=2, default=str).encode("utf-8"),
            file_name=f"work_order_{defect['defect_id']}.json",
            mime="application/json",
        )
with col2:
    if st.button("Export COBie rows"):
        st.info("Exporting COBie rows for this defect...")
with col3:
    if st.button("Request additional survey"):
        if recommendations:
            top = recommendations[0]
            st.info(f"Survey request queued: deploy **{top['modality']}**.")
        else:
            st.info("No further surveys recommended.")
