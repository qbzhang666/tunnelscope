"""
Report — page 8
===============

One click turns the whole session into a board-ready PDF: KPIs, the
BIM 3-D model image, the full defect register, a case file per defect
(evidence → FMEA chain → prescribed intervention → cost build-up),
survey coverage, and the standards library behind the prescriptions.

LaTeX is compiled locally (MiKTeX / TeX Live), following the same
generator pattern as the Tri-HB app. If no TeX engine is installed
the .tex source and figures are offered instead.
"""

import streamlit as st

from utils.ontology_loader import load_ontology, load_defects
from utils.styling import apply_custom_css
from utils.explainers import render_plain_guide
from utils.gis import list_tunnels
from utils.bim import get_tunnel_record
from utils.report import generate_report

apply_custom_css()

if "graph" not in st.session_state:
    st.session_state.graph = load_ontology()
    st.session_state.defects = load_defects(st.session_state.graph)

st.title("Report")
st.caption(
    "Generate a single PDF capturing everything in this session — "
    "inputs, outputs, the BIM model image, and every defect's case "
    "file — so nobody has to click through the app to see the results."
)

render_plain_guide(
    "Pick the tunnel, press **Generate report**, download the PDF. "
    "Defects registered via Ingest this session are included "
    "automatically."
)

# -----------------------------------------------------------------------------
# Options
# -----------------------------------------------------------------------------
tunnels = list_tunnels()
if not tunnels:
    st.error("No tunnel geometry found — check data/tunnel_geometry.json.")
    st.stop()
label_to_tunnel = {t["label"]: t for t in tunnels}
labels = list(label_to_tunnel.keys())
# Default to the tunnel chosen in the sidebar so the report follows the
# asset the operator is working on — not always Tunnel A.
active_label = st.session_state.get("current_tunnel")
default_idx = labels.index(active_label) if active_label in labels else 0

col1, col2 = st.columns([2, 2])
with col1:
    picked_label = st.selectbox(
        "Tunnel", options=labels, index=default_idx,
        help="Defaults to the active tunnel in the sidebar. The report "
             "covers this tunnel and the defects logged against it.",
    )
with col2:
    include_cases = st.checkbox(
        "Include per-defect case files",
        value=True,
        help="Evidence, FMEA chain, prescribed intervention and cost "
             "build-up for every defect. Uncheck for a short summary-only "
             "report.",
    )

tunnel = label_to_tunnel[picked_label]
tunnel_id = tunnel["tunnel_id"]
defects = [d for d in st.session_state.defects
           if d.get("tunnel_id", "TUN-A") == tunnel_id]

st.caption(
    f"Report will cover **{len(defects)} defect(s)** on "
    f"**{picked_label}** — including any registered this session."
)
if not defects:
    st.warning(
        f"**{picked_label}** has no defects registered yet, so the report "
        f"will be a setup summary — title, BIM model image and tunnel "
        f"parameters, with an empty defect register. Log findings on the "
        f"**4 · Ingest** page first, then come back and regenerate."
    )

if st.button("Generate report", type="primary"):
    with st.spinner(
        "Building LaTeX, rendering the BIM image, compiling the PDF — "
        "the first run may take a minute while MiKTeX fetches packages…"
    ):
        st.session_state.report_artifacts = generate_report(
            tunnel=tunnel,
            bim_tunnel=get_tunnel_record(tunnel_id),
            defects=defects,
            include_case_files=include_cases,
        )

art = st.session_state.get("report_artifacts")
if art:
    if art["pdf"]:
        st.success(
            f"Report compiled — {len(art['pdf']) / 1e6:.1f} MB PDF, "
            f"including the BIM model image and "
            f"{'per-defect case files' if include_cases else 'summary sections'}."
        )
    else:
        st.warning(
            "PDF could not be compiled on this machine — download the "
            "LaTeX source / ZIP below and compile elsewhere.\n\n"
            f"Details: {art['message']}"
        )

    c1, c2, c3 = st.columns(3)
    with c1:
        if art["pdf"]:
            st.download_button(
                "📄 Download PDF report",
                data=art["pdf"],
                file_name=f"{art['jobname']}.pdf",
                mime="application/pdf",
            )
    with c2:
        st.download_button(
            "Download LaTeX source (.tex)",
            data=art["tex"].encode("utf-8"),
            file_name=f"{art['jobname']}.tex",
            mime="application/x-tex",
        )
    with c3:
        st.download_button(
            "Download ZIP (tex + figures)",
            data=art["zip"],
            file_name=f"{art['jobname']}_bundle.zip",
            mime="application/zip",
        )

    with st.expander("Preview — BIM model image used in the report"):
        st.image(art["png"], width="stretch")

st.caption(
    "The report's References section cites the standards behind every "
    "prescription — browse and download them on the 📚 **Standards "
    "Library** page (step 7)."
)
