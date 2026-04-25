"""
Tunnel Digital Twin — Operator Dashboard
=========================================
Main Streamlit application entry point.

Run locally:
    streamlit run app.py

This is the human-facing interface for a serviceability-oriented
multimodal maintenance digital twin. It queries a populated ontology
(OWL/Turtle) through rdflib, and displays defect records, FMEA chains,
and prescribed interventions.
"""

import streamlit as st
from pathlib import Path

from utils.ontology_loader import load_ontology, load_defects
from utils.styling import apply_custom_css

# -----------------------------------------------------------------------------
# Page configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Tunnel DT — Transurban",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_custom_css()

# -----------------------------------------------------------------------------
# Session state initialisation
# -----------------------------------------------------------------------------
if "ontology_loaded" not in st.session_state:
    st.session_state.ontology_loaded = False
if "selected_defect_id" not in st.session_state:
    st.session_state.selected_defect_id = None
if "current_tunnel" not in st.session_state:
    st.session_state.current_tunnel = "Tunnel_A"

# -----------------------------------------------------------------------------
# Sidebar — global navigation and ontology status
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🛣️ Tunnel DT")
    st.caption("Serviceability-Oriented Digital Twin")
    st.divider()

    tunnel_choice = st.selectbox(
        "Active tunnel",
        options=["Tunnel_A", "Tunnel_B", "Tunnel_C"],
        index=0,
        help="Select which tunnel's data to display.",
    )
    st.session_state.current_tunnel = tunnel_choice

    st.divider()

    # Load ontology
    if not st.session_state.ontology_loaded:
        with st.spinner("Loading ontology..."):
            try:
                g = load_ontology()
                defects = load_defects(g)
                st.session_state.graph = g
                st.session_state.defects = defects
                st.session_state.ontology_loaded = True
            except Exception as e:
                st.error(f"Failed to load ontology: {type(e).__name__}: {str(e)}")
                # Set empty defects to allow app to continue
                st.session_state.defects = []
                st.session_state.ontology_loaded = True

    st.markdown("**Ontology status**")
    st.success(f"✓ Loaded — {len(st.session_state.graph)} triples")
    st.caption(f"{len(st.session_state.defects)} defect instances")

    st.divider()
    st.caption(
        "Built for the paper *Serviceability-oriented Multimodal "
        "Data Integration for Tunnel Maintenance Digital Twins in "
        "the Australian Context*."
    )

# -----------------------------------------------------------------------------
# Main landing page — overview
# -----------------------------------------------------------------------------
st.title("Tunnel A — operational overview")
st.caption(
    f"Defects detected, prioritised, and traced to FMEA chains. "
    f"Data as of inspection campaign 2024-03-15."
)

# Key metrics
if "defects" not in st.session_state:
    st.error("ERROR: 'defects' not found in session state. The ontology loader may have failed.")
    st.write("Debug - session state keys:", list(st.session_state.keys()) if hasattr(st, 'session_state') else "No session state")
    st.stop()

defects = st.session_state.defects
active_defects = [d for d in defects if d.get("status") == "Active"]
high_priority = [d for d in active_defects if d.get("priority") == "HIGH"]
completeness_ok = [
    d for d in active_defects if d.get("completeness_score", 0) >= 0.75
]
total_cost = sum(d.get("estimated_cost_aud", 0) for d in active_defects)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(
        "Active defects",
        len(active_defects),
        help="Defects currently requiring tracking or intervention.",
    )
with col2:
    st.metric(
        "High priority",
        len(high_priority),
        help="Action required within 30 days.",
    )
with col3:
    coverage_pct = (
        int(100 * len(completeness_ok) / len(active_defects))
        if active_defects
        else 0
    )
    st.metric(
        "FMEA coverage",
        f"{coverage_pct}%",
        help="Defects with diagnostic completeness ≥ 3/4.",
    )
with col4:
    st.metric(
        "Est. cost",
        f"${total_cost / 1e6:.2f}M",
        help="Estimated intervention cost over the next 12 months.",
    )

st.divider()

# Navigation hint
st.info(
    "Use the **Pages** menu in the sidebar to navigate: "
    "**Defect Register** for a ranked list, **Defect Detail** for the "
    "full FMEA chain of a single defect, **SPARQL Console** for direct "
    "queries, and **CV → COBie Bridge** for the defect semantic "
    "extraction pipeline."
)

# Section coverage bars
st.subheader("Multimodal coverage by tunnel section")

sections = [
    ("Section 1 (K248+500 – K249+200)", 95, "#1D9E75"),
    ("Section 2 (K249+200 – K249+900)", 78, "#BA7517"),
    ("Section 3 (K249+900 – K250+600)", 52, "#E24B4A"),
    ("Section 4 (K250+600 – K251+300)", 67, "#BA7517"),
]

for label, pct, colour in sections:
    col_a, col_b, col_c = st.columns([3, 8, 1])
    with col_a:
        st.write(label)
    with col_b:
        st.progress(pct / 100)
    with col_c:
        st.write(f"{pct}%")

st.caption(
    "Coverage = percentage of ring assets with evidence from at least "
    "three of four modalities (RGB, RGBD, Thermal, GPR). Low-coverage "
    "sections are candidates for targeted follow-up survey."
)

st.divider()

# Top priority defects preview
st.subheader("Top priority defects")
st.caption(
    "Ranked by condition state and diagnostic completeness. "
    "Click a row to view the full FMEA chain."
)

top_defects = sorted(
    high_priority,
    key=lambda d: (-d.get("completeness_score", 0), d.get("discovered_on", "")),
)[:5]

for d in top_defects:
    with st.container():
        col1, col2, col3, col4, col5 = st.columns([1, 4, 1, 1, 1])
        with col1:
            st.code(d["defect_id"], language=None)
        with col2:
            st.write(f"**{d['description']}**")
            st.caption(
                f"Ring {d['ring_id']} · K{d['chainage_m']:.0f}m · {d['position']}"
            )
        with col3:
            score = d.get("completeness_score", 0)
            score_frac = f"{int(score * 4)}/4"
            st.metric("Completeness", score_frac, label_visibility="collapsed")
        with col4:
            st.markdown(f":red[**{d['priority']}**]")
        with col5:
            st.write(f"${d.get('estimated_cost_aud', 0):,}")
