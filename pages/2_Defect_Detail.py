"""
Defect Detail — page 2
======================

Shows the full FMEA reasoning chain for a single defect, including:
    - Modality evidence matrix (RGB, RGBD, Thermal, GPR)
    - Chain traversal: Component → Mechanism → Defect → Indicator →
      Cause → Threshold → Intervention
    - Prescribed intervention with materials, deadline, cost, standards ref
    - Completeness score and missing-modality recommendations
    - Work order generation and COBie export
"""

import streamlit as st
import json

from utils.ontology_loader import (
    load_ontology, load_defects, get_defect_by_id,
    get_fmea_chain, get_modality_evidence,
)
from utils.fmea_chain import (
    compute_completeness, recommend_missing_modality, decision_pathway,
    MODALITY_LEVELS, MODALITY_LIMITATIONS,
)
from utils.styling import apply_custom_css

st.set_page_config(page_title="Defect Detail", layout="wide")
apply_custom_css()

if "graph" not in st.session_state:
    st.session_state.graph = load_ontology()
    st.session_state.defects = load_defects(st.session_state.graph)

# -----------------------------------------------------------------------------
# Defect selector
# -----------------------------------------------------------------------------
defects = st.session_state.defects
defect_ids = [d["defect_id"] for d in defects]

default_id = st.session_state.get("selected_defect_id") or (
    defect_ids[0] if defect_ids else None
)

if not defect_ids:
    st.warning("No defects in the ontology. Load sample data or populate "
               "the ontology first.")
    st.stop()

selected_id = st.selectbox(
    "Select defect",
    options=defect_ids,
    index=defect_ids.index(default_id) if default_id in defect_ids else 0,
)

defect = next((d for d in defects if d["defect_id"] == selected_id), {})
if not defect:
    st.error(f"Defect {selected_id} not found.")
    st.stop()

# -----------------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------------
st.title(f"{defect['defect_id']} — {defect['description']}")
st.caption(
    f"Ring {defect['ring_id']} · Chainage K{defect['chainage_m']:.0f}m · "
    f"{defect['position']} · Discovered {defect.get('discovered_on', 'unknown')}"
)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Defect type", defect["defect_type"])
with col2:
    st.metric("Priority", defect.get("priority", "—"))
with col3:
    score = defect.get("completeness_score", 0)
    st.metric("FMEA completeness", f"{int(score * 4)}/4")
with col4:
    cost = defect.get("estimated_cost_aud", 0)
    st.metric("Est. cost", f"${cost:,}" if cost else "Pending")

st.divider()

# -----------------------------------------------------------------------------
# Modality evidence matrix
# -----------------------------------------------------------------------------
st.subheader("Multimodal evidence")
st.caption(
    "What each sensing modality contributes to the FMEA chain for this "
    "defect. Green = evidence present, orange = partial, red = missing "
    "but required."
)

evidence = defect.get("modality_evidence", {})
cols = st.columns(4)
for i, modality in enumerate(["RGB", "RGBD", "Thermal", "GPR"]):
    with cols[i]:
        mod_data = evidence.get(modality, {})
        present = bool(mod_data)
        st.markdown(f"**{modality}**")
        if present:
            status = "✓ " + mod_data.get("status", "Confirmed")
            st.success(status)
            if "finding" in mod_data:
                st.caption(mod_data["finding"])
            if "fmea_level" in mod_data:
                st.caption(f"Level: {mod_data['fmea_level']}")
        else:
            st.error("⚠ Missing")
            # Check if this modality can actually detect this defect type
            limitations = MODALITY_LIMITATIONS.get(modality, [])
            defect_type_lower = defect["defect_type"].lower()
            if any(lim in defect_type_lower for lim in limitations):
                st.caption(f"Cannot detect this defect type")
            else:
                st.caption("Deployment recommended")

# -----------------------------------------------------------------------------
# Completeness assessment
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Diagnostic completeness assessment")

available_modalities = [m for m in ["RGB", "RGBD", "Thermal", "GPR"]
                        if evidence.get(m)]
score, covered, missing = compute_completeness(
    defect["defect_type"], available_modalities
)
pathway = decision_pathway(score)

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Levels covered**")
    for level in covered:
        st.markdown(f"✓ {level}")
    if missing:
        st.markdown("**Levels missing**")
        for level in missing:
            st.markdown(f":red[✗ {level}]")

with col2:
    st.markdown(f"**Decision pathway:** {pathway['pathway']}")
    st.markdown(f"**Confidence:** {pathway['confidence']}")
    st.info(pathway["action"])

    recommendations = recommend_missing_modality(
        defect["defect_type"], available_modalities
    )
    if recommendations:
        st.markdown("**Recommended additional surveys**")
        for rec in recommendations[:3]:
            st.markdown(f"- Deploy **{rec['modality']}** — {rec['rationale']}")

# -----------------------------------------------------------------------------
# FMEA reasoning chain
# -----------------------------------------------------------------------------
st.divider()
st.subheader("FMEA reasoning chain")

chain_data = defect.get("fmea_chain", [])
if not chain_data:
    # Build from individual fields as fallback
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
         "value": defect.get("indicators_summary", ""),
         "source": "tun:hasIndicator"},
        {"step": "5. Potential cause",
         "value": defect.get("potential_cause", "Not yet determined"),
         "source": "tun:hasPotentialCause"},
        {"step": "6. Threshold triggered",
         "value": defect.get("threshold_triggered", ""),
         "source": defect.get("threshold_reference", "")},
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
# Prescribed intervention
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Prescribed intervention")

interventions = defect.get("prescribed_interventions", [])
if not interventions:
    st.info("No intervention prescribed — completeness insufficient or "
            "defect is below action threshold.")
else:
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
            "decision_pathway": pathway,
            "approval_status": "PENDING_ENGINEER_REVIEW",
        }
        st.download_button(
            "Download work order (JSON)",
            json.dumps(work_order, indent=2).encode("utf-8"),
            file_name=f"work_order_{defect['defect_id']}.json",
            mime="application/json",
        )
with col2:
    if st.button("Export COBie rows"):
        st.info("Exporting COBie rows for this defect...")
with col3:
    if st.button("Request additional survey"):
        st.info("Survey request queued.")
