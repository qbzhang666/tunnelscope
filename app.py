"""
Tunnel Digital Twin — Operator Dashboard
=========================================
Main Streamlit application entry point and page router.

Run locally (Windows, one command):
    run_local.cmd          # sets up an isolated env on first run, then launches
    # or, if your environment is already set up:
    streamlit run app.py
    # See RUN_LOCAL.md for details.

Deployed at:
    https://amandahuang-336-tunnel-dt2026-app-zmguxo.streamlit.app/

This is the human-facing interface for a serviceability-oriented
multimodal tunnel maintenance digital twin. It queries a populated
ontology (OWL/Turtle) through rdflib and presents defect records,
FMEA chains, and prescribed interventions.

Navigation uses st.navigation (MPA v2) so the sidebar shows the pages
in numbered workflow order, grouped by purpose — the page list itself
tells a first-time user where to start. The files in pages/ remain
standalone-runnable (e.g. for AppTest), but their sidebar order,
labels and icons are defined here.

Architecture:
    Protégé (authoring)
        │
        ▼  OWL/Turtle file
    ontology/tunnel_maintenance.ttl
        │
        ▼  rdflib loads into memory
    This Streamlit app
        │
        ├─ SPARQL queries on page load
        └─ Operator views defects, FMEA chains, interventions
"""

import sys

import pandas as pd
import streamlit as st

from utils.ontology_loader import load_ontology, load_defects
from utils.styling import apply_custom_css
from utils.gis import list_tunnels
from utils.cost_model import effective_cost
from utils.explainers import (
    render_logic_pipeline, render_glossary, render_user_workflow,
)

# -----------------------------------------------------------------------------
# Page configuration — MUST be the first Streamlit call
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Tunnel DT — Transurban",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://github.com/amandahuang-336/tunnel-dt2026",
        "Report a bug": "https://github.com/amandahuang-336/tunnel-dt2026/issues",
        "About": (
            "Tunnel Digital Twin operator dashboard, accompanying the paper "
            "*Serviceability-oriented Multimodal Data Integration for Tunnel "
            "Maintenance Digital Twins in the Australian Context*."
        ),
    },
)

apply_custom_css()


# -----------------------------------------------------------------------------
# Session state initialisation
# -----------------------------------------------------------------------------
def init_session_state():
    """Initialise session state with sensible defaults."""
    defaults = {
        "ontology_loaded": False,
        "selected_defect_id": None,
        "current_tunnel": "Tunnel A",
        "graph": None,
        "defects": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()


# -----------------------------------------------------------------------------
# Ontology loader — wrapped to handle errors gracefully
# -----------------------------------------------------------------------------
def ensure_ontology_loaded():
    """Load ontology and defect data into session state if not already done."""
    if st.session_state.ontology_loaded:
        return True

    try:
        with st.spinner("Loading ontology and defect data..."):
            graph = load_ontology()
            defects = load_defects(graph)
            st.session_state.graph = graph
            st.session_state.defects = defects
            st.session_state.ontology_loaded = True
        return True
    except Exception as e:
        st.error(f"Failed to load ontology: {e}")
        st.exception(e)
        return False


# -----------------------------------------------------------------------------
# Sidebar — compact: tunnel selector plus one collapsed System expander.
# Page navigation itself is rendered by st.navigation above this content.
# -----------------------------------------------------------------------------
def render_sidebar():
    with st.sidebar:
        st.markdown("#### 🛣️ Tunnel DT")
        st.caption("Serviceability-oriented digital twin")

        # Built-in tunnels plus any the user registered on Tunnel Setup.
        tunnel_labels = [t["label"] for t in list_tunnels()] or ["Tunnel A"]
        tunnel_choice = st.selectbox(
            "Active tunnel",
            options=tunnel_labels,
            index=0,
            help=(
                "Tunnel A carries the full demo dataset. "
                "Add your own tunnel on the **Tunnel Setup** page."
            ),
        )
        st.session_state.current_tunnel = tunnel_choice

        with st.expander("System", expanded=False):
            if st.session_state.ontology_loaded and st.session_state.graph is not None:
                st.caption(
                    f"✓ Ontology loaded — "
                    f"{len(st.session_state.graph):,} triples · "
                    f"{len(st.session_state.defects)} defect instances"
                )
            else:
                st.caption("Ontology not loaded")
            if st.button("Reload ontology", width="stretch"):
                st.session_state.ontology_loaded = False
                st.cache_data.clear()
                st.cache_resource.clear()
                st.rerun()
            st.caption(
                f"Python {sys.version.split()[0]} · "
                f"Streamlit {st.__version__}"
            )
            st.caption(
                "Companion app to the paper *Serviceability-oriented "
                "Multimodal Data Integration for Tunnel Maintenance "
                "Digital Twins in the Australian Context*."
            )


# -----------------------------------------------------------------------------
# Overview page content
# -----------------------------------------------------------------------------
def render_overview():
    st.title(f"{st.session_state.current_tunnel} — operational overview")
    st.caption(
        "Defects detected, prioritised, and traced to FMEA chains. "
        "Data as of inspection campaign 2024-03-15."
    )

    # Executive layer — usage steps and workflow first, the system's
    # logic and glossary in the second tab.
    tab_use, tab_logic = st.tabs(["🧭 How to use", "⚙️ How it works"])
    with tab_use:
        render_user_workflow()
    with tab_logic:
        render_logic_pipeline()
        render_glossary()

    defects = st.session_state.defects
    if not defects:
        st.warning(
            "No defect data loaded. Check that "
            "`data/defects_tunnel_a.json` exists and is valid."
        )
        return

    # Filter by status
    active_defects = [d for d in defects if d.get("status") == "Active"]
    high_priority = [d for d in active_defects if d.get("priority") == "HIGH"]
    completeness_ok = [
        d for d in active_defects if d.get("completeness_score", 0) >= 0.75
    ]
    # Engineer-recorded estimates where they exist, unit-rate model
    # estimates otherwise — so the exposure number has no silent $0 gaps.
    total_cost = sum(effective_cost(d)[0] for d in active_defects)

    # -----------------------------------------------------------------------------
    # Top metrics row
    # -----------------------------------------------------------------------------
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "Open defects",
            len(active_defects),
            help="Issues currently tracked or awaiting repair.",
        )
    with col2:
        st.metric(
            "Need action ≤ 30 days",
            len(high_priority),
            delta=f"{len(high_priority)} need attention" if high_priority else None,
            delta_color="inverse",
            help="HIGH-priority defects.",
        )
    with col3:
        coverage_pct = (
            int(100 * len(completeness_ok) / len(active_defects))
            if active_defects
            else 0
        )
        st.metric(
            "Diagnosis confidence",
            f"{coverage_pct}%",
            help="Open defects with ≥3 of 4 sensing sources agreeing "
                 "(FMEA coverage).",
        )
    with col4:
        st.metric(
            "12-month cost exposure",
            f"${total_cost / 1e6:.2f}M",
            help="Estimated cost of prescribed repairs — engineer "
                 "estimates where recorded, unit-rate model otherwise.",
        )

    # One-sentence interpretation so the numbers need no translation.
    if high_priority:
        st.warning(
            f"**Bottom line:** {len(high_priority)} of "
            f"{len(active_defects)} open defects need action within "
            f"30 days — est. ${total_cost / 1e6:.2f}M. See the "
            f"**Defect Register**."
        )
    else:
        st.success(
            f"**Bottom line:** nothing requires action within 30 days. "
            f"{len(active_defects)} defects tracked — est. exposure "
            f"${total_cost / 1e6:.2f}M."
        )

    st.divider()

    # -----------------------------------------------------------------------------
    # Section coverage — one compact row
    # -----------------------------------------------------------------------------
    st.subheader("Survey coverage by tunnel section")
    st.caption(
        "🟢 well surveyed · 🟡 partial · 🔴 needs follow-up survey — "
        "coverage = rings with evidence from ≥3 of 4 sensing sources."
    )

    sections = [
        ("Section 1", "K248+500 – K249+200", 95, "🟢"),
        ("Section 2", "K249+200 – K249+900", 78, "🟡"),
        ("Section 3", "K249+900 – K250+600", 52, "🔴"),
        ("Section 4", "K250+600 – K251+300", 67, "🟡"),
    ]

    cols = st.columns(4)
    for col, (name, span, pct, icon) in zip(cols, sections):
        with col:
            st.markdown(f"{icon} **{name}** · {pct}%")
            st.progress(pct / 100)
            st.caption(span)

    st.divider()

    # -----------------------------------------------------------------------------
    # Top priority defects — compact table
    # -----------------------------------------------------------------------------
    st.subheader("Top priority defects")
    st.caption(
        "Five most urgent, ranked by condition and evidence strength. "
        "Evidence 4/4 = corroborated by every applicable source. "
        "Full list: **Defect Register**."
    )

    top_defects = sorted(
        high_priority,
        key=lambda d: (
            -d.get("completeness_score", 0),
            d.get("discovered_on", ""),
        ),
    )[:5]

    if not top_defects:
        st.info("No high priority defects currently identified.")
        return

    rows = []
    for d in top_defects:
        cost, basis = effective_cost(d)
        rows.append({
            "ID": d["defect_id"],
            "Defect": d["description"],
            "Where": f"Ring {d['ring_id']} · K{d['chainage_m']:.0f}m · "
                     f"{d.get('position', '—')}",
            "Evidence": f"{int(d.get('completeness_score', 0) * 4)}/4",
            "Priority": d.get("priority", "—"),
            "Est. cost (AUD)": cost,
            "Basis": basis,
        })
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "Est. cost (AUD)": st.column_config.NumberColumn(format="$%d"),
        },
    )
    st.caption(
        "Cost basis: **engineer** = recorded estimate · **modelled** = "
        "unit-rate model (build-up on the Defect Detail page)."
    )


# -----------------------------------------------------------------------------
# Navigation — numbered workflow order, grouped by purpose. This replaces
# Streamlit's automatic pages/ nav, so labels and grouping are explicit.
# -----------------------------------------------------------------------------
# Groups follow the asset lifecycle: set up the tunnel, see its BIM
# model, register and diagnose defects (with the standards one step
# away), and finish with the report that summarises it all.
nav = st.navigation({
    "Start here": [
        st.Page(render_overview, title="1 · Overview", icon="🏠",
                url_path="overview", default=True),
    ],
    "Set up the asset": [
        st.Page("pages/6_Tunnel_Setup.py",
                title="2 · Tunnel Setup", icon="🛠️"),
        st.Page("pages/7_BIM_3D_Viewer.py",
                title="3 · 3D Tunnel (BIM)", icon="🧊"),
    ],
    "Inspect & diagnose": [
        st.Page("pages/0_Ingest.py",
                title="4 · Ingest a finding", icon="📤"),
        st.Page("pages/1_Defect_Register.py",
                title="5 · Defect Register", icon="🗺️"),
        st.Page("pages/2_Defect_Detail.py",
                title="6 · Defect Detail", icon="📋"),
        st.Page("pages/9_Standards_Library.py",
                title="7 · Standards Library", icon="📚"),
    ],
    "Specialists": [
        st.Page("pages/3_SPARQL_Console.py", title="SPARQL Console", icon="🔎"),
        st.Page("pages/4_CV_to_COBie_Bridge.py",
                title="CV → COBie Bridge", icon="🌉"),
        st.Page("pages/5_Ontology_Browser.py",
                title="Ontology Browser", icon="🧩"),
    ],
    "Final step": [
        st.Page("pages/8_Report.py", title="8 · Report (PDF)", icon="📄"),
    ],
})

render_sidebar()

if not ensure_ontology_loaded():
    st.stop()

try:
    nav.run()
except Exception as exc:
    st.error("⚠️ The dashboard encountered an unexpected error.")
    st.exception(exc)
    st.markdown("---")
    st.caption(
        "If this persists, please report the issue at "
        "[GitHub Issues](https://github.com/amandahuang-336/tunnel-dt2026/issues)."
    )
