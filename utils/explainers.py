"""
Plain-language explainer components
===================================

A thin presentation layer that translates the app for clients and
senior managers — kept deliberately terse so it orients without adding
reading load:

1. render_plain_guide — one "In plain English" line at the top of
   each page.
2. render_logic_pipeline — the system's logic as four short cards
   (Detect, Diagnose, Decide, Do), with the full data-flow diagram
   one click away.
3. render_glossary — collapsed two-column jargon translator.

Nothing here reads or changes data.
"""

import streamlit as st


def render_plain_guide(text: str) -> None:
    """One-line plain-English orientation for the top of a page."""
    st.caption(f"💼 **In plain English:** {text}")


# User journey through the app's pages: solid = the main capture-to-report
# path; dashed = optional reference tools (6-9) that branch off it. The
# Report & Presentation summary gets the primary fill as the goal.
_USERFLOW_DOT = """
digraph userflow {
    rankdir=LR;
    bgcolor="transparent";
    node [shape=box, style="rounded,filled", fillcolor="#F5F4EF",
          color="#534AB7", fontcolor="#2C2C2A", fontname="Helvetica",
          fontsize=12, margin="0.22,0.14"];
    edge [color="#534AB7", penwidth=1.3, arrowsize=0.8];

    setup    [label="① Tunnel Setup\\nlocation & dimensions"];
    bim      [label="② 3D Tunnel\\nBIM model"];
    ingest   [label="③ Ingest\\nregister defects"];
    register [label="④ Defect Register\\nwhat & where"];
    detail   [label="⑤ Defect Detail\\ndiagnosis, repair,\\nwork order"];
    library  [label="⑥ Standards Library\\nsource documents",
              style="rounded,filled,dashed"];
    sparql   [label="⑦ SPARQL Console\\nverify any figure",
              style="rounded,filled,dashed"];
    cobie    [label="⑧ CV → COBie\\nAI pipeline",
              style="rounded,filled,dashed"];
    ontology [label="⑨ Ontology Browser\\nknowledge model",
              style="rounded,filled,dashed"];
    report   [label="Report and Presentation\\nPDF + slide deck",
              fillcolor="#534AB7", fontcolor="#FFFFFF"];

    setup -> bim -> ingest -> register -> detail -> report;
    detail -> library [style=dashed];
    detail -> sparql [style=dashed];
    ingest -> cobie [style=dashed];
    detail -> ontology [style=dashed];
}
"""

def render_user_workflow() -> None:
    """The asset-lifecycle steps with the journey diagram below, full
    width so it renders at a readable size. Step numbers match the
    sidebar's numbered page labels."""
    st.markdown(
        "**Set up once:** ① **Tunnel Setup** — location & dimensions · "
        "② **3D Tunnel (BIM)** — check the model.  \n"
        "**Each inspection:** ③ **Ingest** findings → ④ **Defect "
        "Register** — what & where → ⑤ **Defect Detail** — diagnosis, "
        "standard-backed repair, work order.  \n"
        "**Optional tools (dashed):** ⑥ **Standards Library** (source "
        "documents) · ⑦ **SPARQL Console** (verify any figure) · "
        "⑧ **CV → COBie** (the AI pipeline) · ⑨ **Ontology Browser** "
        "(the knowledge model).  \n"
        "**Wrap up:** **Report and Presentation** — the summary deliverable "
        "(PDF report + slide deck)."
    )
    st.caption(
        "Steps ⑥–⑨ are optional reference tools (shown dashed) — use them "
        "anytime. This Overview tracks the headline numbers throughout."
    )
    st.graphviz_chart(_USERFLOW_DOT, width="stretch")


# Colors match .streamlit/config.toml theme (primary #534AB7,
# secondary background #F5F4EF, text #2C2C2A).
_PIPELINE_DOT = """
digraph pipeline {
    rankdir=LR;
    bgcolor="transparent";
    node [shape=box, style="rounded,filled", fillcolor="#F5F4EF",
          color="#534AB7", fontcolor="#2C2C2A", fontname="Helvetica",
          fontsize=12, margin="0.22,0.14"];
    edge [color="#534AB7", penwidth=1.3, arrowsize=0.8];

    survey  [label="Tunnel survey\\nphoto, 3-D depth,\\nthermal, radar"];
    extract [label="AI extraction\\nfinds, measures and\\nlocates each defect"];
    records [label="Standard records\\none asset record per\\ndefect (COBie format)"];
    kb      [label="Knowledge base\\nlinks defect to cause,\\nrisk and repair"];
    rank    [label="Risk ranking\\nurgency scored against\\nroad-agency standards"];
    plan    [label="Maintenance plan\\nwork orders with method,\\ndeadline and cost"];

    survey -> extract -> records -> kb -> rank -> plan;
}
"""

_STORY_STEPS = [
    ("🔍", "Detect", "Sensors survey the tunnel; AI finds and measures defects."),
    ("🧠", "Diagnose", "Each defect is traced to its engineering cause (FMEA)."),
    ("⚖️", "Decide", "Standards-based rules rank urgency and pick the repair."),
    ("🔧", "Do", "Costed work orders feed the maintenance programme."),
]


def render_logic_pipeline() -> None:
    """The system's logic as four short cards, for the Overview page."""
    cols = st.columns(4)
    for col, (icon, title, body) in zip(cols, _STORY_STEPS):
        with col:
            with st.container(border=True):
                st.markdown(f"**{icon} {title}**")
                st.caption(body)

    with st.expander("Full data flow — survey to work order"):
        st.graphviz_chart(_PIPELINE_DOT)
        st.caption(
            "Read right to left for audit: every work order traces back "
            "to raw survey evidence."
        )


_GLOSSARY = [
    ("Knowledge base / ontology",
     "the engineering knowledge the system reasons with"),
    ("FMEA", "standard cause-and-effect analysis of failures"),
    ("COBie", "industry-standard format for asset records"),
    ("SPARQL", "query language for the knowledge base"),
    ("Modality", "one sensing source: photo, depth, thermal or radar"),
    ("Ring / chainage", "tunnel address — lining hoop / metres from entrance"),
    ("Completeness", "evidence held vs ideal (4/4 = fully corroborated)"),
    ("Priority", "rule-based urgency from moisture and severity codes — "
     "HIGH means act within 30 days"),
    ("Estimated cost",
     "engineer figure where recorded, else unit-rate model estimate"),
]


def render_glossary() -> None:
    """Compact jargon translator, collapsed by default."""
    with st.expander("📖 Jargon translator"):
        left, right = st.columns(2)
        for i, (term, meaning) in enumerate(_GLOSSARY):
            target = left if i % 2 == 0 else right
            target.markdown(f"**{term}** — {meaning}")


def render_priority_cost_help() -> None:
    """How priority and estimated cost are determined — shown wherever
    those two columns appear, so the basis is never a mystery."""
    with st.expander("ℹ️ How priority and cost are determined"):
        st.markdown(
            "**Priority** is rule-based, following AASHTO / Austroads "
            "condition coding: active water ingress (moisture code "
            "GS = gushing, F = flowing) **or** spalling at/past the "
            "reinforcement (AASHTO grade S-3 / S-4) → **HIGH** — act "
            "within 30 days. Moderate spalling (S-2) or damp surface "
            "(M) → **MEDIUM**. Otherwise **LOW**. The rule is "
            "`assign_priority()` in the CV → COBie bridge; operators "
            "can override it when registering a defect, and an "
            "engineer signs off on every work order.\n\n"
            "**Estimated cost** — engineer-recorded figures where they "
            "exist; otherwise a transparent **unit-rate model**: the "
            "defect type's repair method (AASHTO/Austroads) × measured "
            "quantity × indicative Australian rates, plus "
            "night-possession mobilisation, adjusted for severity, "
            "active water and crown access, with a contingency band "
            "that widens when evidence completeness is low. Every "
            "figure's full build-up is on the **Defect Detail** page. "
            "Default rates are placeholders — calibrate them to your "
            "maintenance contract."
        )
