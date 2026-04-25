"""
Tunnel Digital Twin — Operator Dashboard
Diagnostic version: surfaces all import/startup errors visibly.
"""

import streamlit as st
import traceback
import sys

st.set_page_config(
    page_title="Tunnel DT — Transurban",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# Wrap the whole startup in a try/except so errors surface to the page
# -----------------------------------------------------------------------------
try:
    from pathlib import Path
    from utils.ontology_loader import load_ontology, load_defects
    from utils.styling import apply_custom_css

    apply_custom_css()

    # Session state
    if "ontology_loaded" not in st.session_state:
        st.session_state.ontology_loaded = False
    if "selected_defect_id" not in st.session_state:
        st.session_state.selected_defect_id = None
    if "current_tunnel" not in st.session_state:
        st.session_state.current_tunnel = "Tunnel_A"

    with st.sidebar:
        st.markdown("### 🛣️ Tunnel DT")
        st.caption("Serviceability-Oriented Digital Twin")
        st.divider()

        tunnel_choice = st.selectbox(
            "Active tunnel",
            options=["Tunnel_A", "Tunnel_B", "Tunnel_C"],
            index=0,
        )
        st.session_state.current_tunnel = tunnel_choice

        st.divider()

        if not st.session_state.ontology_loaded:
            with st.spinner("Loading ontology..."):
                g = load_ontology()
                defects = load_defects(g)
                st.session_state.graph = g
                st.session_state.defects = defects
                st.session_state.ontology_loaded = True

        st.markdown("**Ontology status**")
        st.success(f"✓ Loaded — {len(st.session_state.graph)} triples")
        st.caption(f"{len(st.session_state.defects)} defect instances")

    st.title("Tunnel A — operational overview")
    st.caption(
        "Defects detected, prioritised, and traced to FMEA chains. "
        "Data as of inspection campaign 2024-03-15."
    )

    defects = st.session_state.defects
    active_defects = [d for d in defects if d.get("status") == "Active"]
    high_priority = [d for d in active_defects if d.get("priority") == "HIGH"]
    completeness_ok = [
        d for d in active_defects if d.get("completeness_score", 0) >= 0.75
    ]
    total_cost = sum(d.get("estimated_cost_aud", 0) for d in active_defects)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Active defects", len(active_defects))
    with col2:
        st.metric("High priority", len(high_priority))
    with col3:
        coverage_pct = (
            int(100 * len(completeness_ok) / len(active_defects))
            if active_defects else 0
        )
        st.metric("FMEA coverage", f"{coverage_pct}%")
    with col4:
        st.metric("Est. cost", f"${total_cost / 1e6:.2f}M")

    st.divider()
    st.info(
        "Use the **Pages** menu in the sidebar to navigate."
    )

except Exception as e:
    st.error("⚠️ The app crashed during startup. Traceback below:")
    st.exception(e)
    st.code(traceback.format_exc(), language="python")
    st.markdown("---")
    st.markdown(f"**Python version:** `{sys.version}`")
    st.markdown(f"**Working directory:** `{Path.cwd() if 'Path' in dir() else 'unknown'}`")