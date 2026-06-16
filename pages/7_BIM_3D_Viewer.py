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
from utils.bim3d import (
    build_tunnel_3d_figure, build_ring_section_figure, DEFAULT_DIAMETER_M,
    DEFAULT_LINING_THICKNESS_M, DEFAULT_SEGMENTS_PER_RING,
    DEFAULT_KEYSTONE_RATIO,
)
from utils.ifc_export import build_ifc, ONTOLOGY_BASE
from utils.cost_model import effective_cost
from utils.scan_import import load_scan, build_scan_figure, SUPPORTED_EXT

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
# Lining geometry — defaults from the BIM as-built record, but editable so
# tunnels with no record (or a different ring build) still model correctly.
# -----------------------------------------------------------------------------
bt = bim_tunnel or {}
with st.expander("Lining geometry (segmental ring)", expanded=False):
    gcol1, gcol2, gcol3, gcol4 = st.columns(4)
    with gcol1:
        g_diameter = st.number_input(
            "Internal diameter (m)", min_value=2.0, max_value=20.0, step=0.5,
            value=float(bt.get("internal_diameter_m") or DEFAULT_DIAMETER_M),
        )
    with gcol2:
        g_thickness = st.number_input(
            "Lining thickness (m)", min_value=0.10, max_value=1.20, step=0.05,
            value=float(bt.get("lining_thickness_m")
                        or DEFAULT_LINING_THICKNESS_M),
        )
    with gcol3:
        g_segments = st.number_input(
            "Segments per ring (incl. keystone)", min_value=3, max_value=14,
            step=1,
            value=int(bt.get("segments_per_ring") or DEFAULT_SEGMENTS_PER_RING),
        )
    with gcol4:
        g_keyratio = st.slider(
            "Keystone width (x standard)", min_value=0.20, max_value=1.00,
            step=0.05, value=DEFAULT_KEYSTONE_RATIO,
        )
    g_show_seg = st.checkbox("Show segment joints & keystone", value=True)
    if bim_tunnel:
        st.caption(
            f"Defaults from the BIM as-built record: "
            f"{bt.get('lining_type', 'segmental lining')} - "
            f"{bt.get('joint_type', '-')}."
        )
    else:
        st.caption(
            "This tunnel has no BIM as-built record yet, so generic defaults "
            "are shown - adjust them to match the real ring build."
        )

# Effective geometry actually drawn (record values, overridden by the inputs).
eff_bim = dict(bim_tunnel or {})
eff_bim["internal_diameter_m"] = float(g_diameter)
eff_bim["lining_thickness_m"] = float(g_thickness)
eff_bim["segments_per_ring"] = int(g_segments)

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
    bim_tunnel=eff_bim,
    defects=plottable,
    colour_by="priority" if colour_by == "Priority" else "type",
    keystone_ratio=float(g_keyratio),
    show_segments=g_show_seg,
)
st.plotly_chart(fig, width="stretch")

src = "BIM as-built" if bim_tunnel else "generic / user-set"
st.caption(
    f"**{len(plottable)} defect(s) shown** on {picked_label}"
    + (f" - {skipped} without a chainage not plotted" if skipped else "")
    + f" - {src} geometry: {g_diameter:.1f} m bore, "
    f"{g_thickness*1000:.0f} mm lining, {int(g_segments)} segments/ring "
    f"(1 keystone). The 3-D length axis is compressed so the cross-section "
    f"stays readable - see the true-scale ring section below."
)

# -----------------------------------------------------------------------------
# True-scale ring cross-section — thickness, segments and keystone un-compressed
# -----------------------------------------------------------------------------
st.subheader("Ring cross-section (true scale)")
sec_fig = build_ring_section_figure(
    float(g_diameter), float(g_thickness), int(g_segments),
    float(g_keyratio), defects=plottable,
)
st.plotly_chart(sec_fig, width="stretch")
st.caption(
    "One ring looking down the tunnel axis, drawn 1:1 - so lining thickness, "
    "segment count, segment arc width and the keystone (K, highlighted) are "
    "all to scale. Dots are this tunnel's defects projected onto the ring "
    "face by their cross-section position. Joints are schematic (equal arcs "
    "+ one keystone); real rings stagger the joints ring-to-ring."
)

# -----------------------------------------------------------------------------
# Upload your own as-built model (scan-to-BIM) — mesh or point cloud
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Upload your own as-built model (scan-to-BIM)")
st.caption(
    "Have a laser scan or scan-to-BIM result? Upload the surface **mesh** "
    "(OBJ / STL / PLY) or **point cloud** (XYZ / PTS / CSV / PLY) to view the "
    "real as-built geometry at true scale. Parsed locally - nothing leaves "
    "your machine."
)
scan_file = st.file_uploader(
    "As-built mesh or point cloud",
    type=list(SUPPORTED_EXT),
    help="Meshes: OBJ, STL, PLY. Point clouds: XYZ, PTS, CSV, PLY. Large "
         "clouds are subsampled for display.",
)
if scan_file is not None:
    try:
        scan = load_scan(scan_file.name, scan_file.getvalue())
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not read '{scan_file.name}': {exc}")
    else:
        st.plotly_chart(build_scan_figure(scan), width="stretch")
        lo, hi = scan["bbox"]
        dims = hi - lo
        meta = (
            f"{scan['n_vertices']:,} vertices"
            + (f", {scan['n_faces']:,} faces" if scan["n_faces"] else "")
            + f" - {scan['kind']} - bounding box "
            f"{dims[0]:.1f} x {dims[1]:.1f} x {dims[2]:.1f} m "
            f"(longest extent {max(dims):.1f} m)."
        )
        st.caption(
            meta + " Shown in the scan's own coordinates at true scale; "
            "defects are not overlaid here because the scan and the digital-"
            "twin chainage frame are not registered to each other."
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

ifc_text = build_ifc(tunnel, eff_bim, plottable)
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
