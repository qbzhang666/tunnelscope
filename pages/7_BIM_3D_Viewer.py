"""
BIM 3D Viewer — page 7
======================

Direct visual answer to "where are the defects?": the tunnel lining
as an interactive 3-D model (diameter from the BIM as-built record),
with every defect plotted at its surveyed chainage and cross-section
position. Hovering a marker shows the defect's ID, type, location,
priority and estimated cost; clicking a legend entry toggles that
group. Colour by urgency or by defect type.

Defects registered through the Ingest page appear here immediately,
on whichever tunnel they were logged against — including tunnels the
user created on the Tunnel Setup page (those render with the default
diameter if they have no BIM record).
"""

import pandas as pd
import streamlit as st

from utils.ontology_loader import load_ontology, load_defects
from utils.styling import apply_custom_css
from utils.explainers import render_plain_guide, render_priority_cost_help
from utils.gis import list_tunnels
from utils.bim import get_tunnel_record
from utils.bim3d import build_tunnel_3d_figure, DEFAULT_DIAMETER_M
from utils.ifc_export import build_ifc, ONTOLOGY_BASE
from utils.cost_model import effective_cost

apply_custom_css()

if "graph" not in st.session_state:
    st.session_state.graph = load_ontology()
    st.session_state.defects = load_defects(st.session_state.graph)

st.title("3D tunnel viewer (BIM)")
st.caption(
    "The tunnel lining as a 3-D model built from the BIM as-built "
    "record, with every defect at its surveyed position."
)

render_plain_guide(
    "Each dot is one defect, placed where it actually is — along the "
    "tunnel and around the cross-section. **Drag** to rotate, "
    "**scroll** to zoom, **hover** a dot for its summary, **click** a "
    "legend entry to hide/show that group."
)

# -----------------------------------------------------------------------------
# Controls
# -----------------------------------------------------------------------------
tunnels = list_tunnels()
if not tunnels:
    st.error("No tunnel geometry found — check data/tunnel_geometry.json.")
    st.stop()
label_to_tunnel = {t["label"]: t for t in tunnels}

col1, col2, col3 = st.columns([2, 1.6, 2])
with col1:
    picked_label = st.selectbox("Tunnel", options=list(label_to_tunnel.keys()))
with col2:
    colour_by = st.radio(
        "Colour by", options=["Priority", "Defect type"], horizontal=True,
    )
with col3:
    priority_filter = st.multiselect(
        "Priority", options=["HIGH", "MEDIUM", "LOW"], default=[],
        placeholder="All priorities",
    )

tunnel = label_to_tunnel[picked_label]
tunnel_id = tunnel["tunnel_id"]
bim_tunnel = get_tunnel_record(tunnel_id)

# -----------------------------------------------------------------------------
# Select defects for this tunnel
# -----------------------------------------------------------------------------
defects = [
    d for d in st.session_state.defects
    if d.get("tunnel_id", "TUN-A") == tunnel_id
]
if priority_filter:
    defects = [d for d in defects if d.get("priority") in priority_filter]

plottable = [d for d in defects if d.get("chainage_m")
             and float(d["chainage_m"]) > 0]
skipped = len(defects) - len(plottable)

# -----------------------------------------------------------------------------
# Figure
# -----------------------------------------------------------------------------
fig = build_tunnel_3d_figure(
    tunnel=tunnel,
    bim_tunnel=bim_tunnel,
    defects=plottable,
    colour_by="priority" if colour_by == "Priority" else "type",
)
st.plotly_chart(fig, width="stretch")

if bim_tunnel:
    bim_facts = (
        f"BIM as-built: Ø{bim_tunnel.get('internal_diameter_m', '—')} m · "
        f"lining {bim_tunnel.get('lining_thickness_m', '—')} m · "
        f"{bim_tunnel.get('segments_per_ring', '—')} segments/ring · "
        f"{bim_tunnel.get('joint_type', '—')}"
    )
else:
    bim_facts = (
        f"No BIM record for this tunnel — generic "
        f"Ø{DEFAULT_DIAMETER_M:.0f} m lining shown"
    )
st.caption(
    f"**{len(plottable)} defect(s) shown** on {picked_label}"
    + (f" · {skipped} without a chainage not plotted" if skipped else "")
    + f" · {bim_facts}. Geometry is schematic — the length axis is "
    f"compressed so the cross-section stays readable."
)

# -----------------------------------------------------------------------------
# Export to IFC (openBIM) — the semantic bridge to the AEC world
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Export to IFC (openBIM)")
st.caption(
    "Industry Foundation Classes file of the model above: the lining "
    "plus every defect as IFC elements. Each defect carries its full "
    "record as a property set (`Pset_TunnelDT_Defect`) and a "
    "classification reference pointing at its **ontology class URI** — "
    "the same identifier the knowledge base reasons with. Opens in any "
    "IFC viewer (BIMvision, Solibri, BlenderBIM, usBIM)."
)

ifc_text = build_ifc(tunnel, bim_tunnel, plottable)
col_dl, col_info = st.columns([1.4, 3])
with col_dl:
    st.download_button(
        "Download IFC model",
        data=ifc_text.encode("ascii", "replace"),
        file_name=f"{tunnel_id}_defects.ifc",
        mime="application/x-step",
    )
with col_info:
    st.caption(
        f"IFC4 · {len(plottable)} defect element(s) + lining · "
        f"classified against `{ONTOLOGY_BASE}`"
    )

with st.expander("How the digital twin maps to IFC"):
    st.markdown(
        "| Digital-twin concept | IFC representation |\n"
        "|---|---|\n"
        "| Tunnel (BIM as-built) | `IfcBuilding` with ObjectType "
        "`Tunnel` — `IfcTunnel` is standardised in the upcoming "
        "IFC 4.4 and slots in here |\n"
        "| Lining geometry | `IfcCircleHollowProfileDef` (Ø and "
        "thickness from the as-built record) swept the tunnel length |\n"
        "| One defect | `IfcBuildingElementProxy` placed at its "
        "chainage and cross-section angle |\n"
        "| Defect record | `Pset_TunnelDT_Defect` — type, ring, "
        "chainage, position, priority, severity, cost, completeness, "
        "status, discovery date |\n"
        "| Defect type | `IfcClassificationReference` → "
        f"`{ONTOLOGY_BASE}#<Type>` via "
        "`IfcRelAssociatesClassification` — the **same URI** the "
        "ontology uses, so the IFC file and the knowledge base stay "
        "semantically linked |\n"
    )

# -----------------------------------------------------------------------------
# The same defects as a compact table, for copy/reporting
# -----------------------------------------------------------------------------
with st.expander("Defects shown, as a table"):
    if not plottable:
        st.info("No defects to list for this tunnel/filter.")
    else:
        rows = []
        for d in plottable:
            cost, basis = effective_cost(d)
            rows.append({
                "ID": d["defect_id"],
                "Type": d.get("defect_type", ""),
                "Where": f"Ring {d.get('ring_id', '?')} · "
                         f"K{float(d['chainage_m']):.0f}m · "
                         f"{d.get('position', '—')}",
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
            "Cost basis: **engineer** = recorded estimate · **modelled** "
            "= unit-rate model (build-up on the Defect Detail page)."
        )

render_priority_cost_help()
