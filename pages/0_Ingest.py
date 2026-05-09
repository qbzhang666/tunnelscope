"""
Ingest — page 0
===============

Single-modality entry point. Operators register a defect from:
    - an inspection image (PNG/JPG/JPEG), or
    - an inspection report (PDF/DOCX/TXT)

REVISED (Rev 6):
- Tunnel selector at the top — operator picks Tunnel A or Tunnel B
  before uploading anything.
- Interactive map below the file uploader. Operator clicks where they
  took the photo. The click resolves to (chainage_m, ring_id, position)
  and pre-fills the form below.
- For the heuristic stub route on text reports, any ring number found
  by regex is cross-checked against the map click — disagreement is
  surfaced to the operator before submission.
"""

from typing import Dict, Optional

import streamlit as st
from streamlit_folium import st_folium

from utils.ontology_loader import load_ontology, load_defects
from utils.styling import apply_custom_css
from utils.ingest import (
    DEFECT_TYPE_OPTIONS, PRIORITY_OPTIONS, POSITION_OPTIONS,
    extract_text_from_upload, heuristic_defect_type_from_filename,
    heuristic_fields_from_text, build_defect_dict,
    build_ingested_defect_id,
)
from utils.gis import (
    list_tunnels, build_ingest_map, click_to_tunnel_location,
    position_from_offset,
)

st.set_page_config(page_title="Ingest", layout="wide")
apply_custom_css()

if "graph" not in st.session_state:
    st.session_state.graph = load_ontology()
    st.session_state.defects = load_defects(st.session_state.graph)

if "ingested_defects" not in st.session_state:
    st.session_state.ingested_defects = []

# Per-session state for the map workflow
if "ingest_picked_location" not in st.session_state:
    st.session_state.ingest_picked_location = None  # type: Optional[Dict]


st.title("Ingest a defect")
st.caption(
    "Register a defect from a single inspection photo or a written "
    "inspection report. Pick the tunnel and click on the map to "
    "locate the defect — ring and chainage are derived from the click."
)

# -----------------------------------------------------------------------------
# Tunnel selector
# -----------------------------------------------------------------------------
tunnels = list_tunnels()
if not tunnels:
    st.error(
        "No tunnel geometry found. Check that "
        "`data/tunnel_geometry.json` exists in the repo."
    )
    st.stop()

tunnel_options = {t["tunnel_id"]: t for t in tunnels}
tunnel_label_to_id = {
    f"{t['label']} — {t['length_m']} m, max depth {t.get('max_depth_m', '—')} m":
        t["tunnel_id"]
    for t in tunnels
}

picked_label = st.radio(
    "Tunnel",
    options=list(tunnel_label_to_id.keys()),
    horizontal=False,
    help="Tunnels A and B are anonymised. Real coordinates are used for "
         "the map; alignment is approximate, traced from public scope maps.",
)
picked_tunnel_id = tunnel_label_to_id[picked_label]
picked_tunnel = tunnel_options[picked_tunnel_id]

# -----------------------------------------------------------------------------
# Click-to-locate map
# -----------------------------------------------------------------------------
st.subheader("Locate the defect on the map")
st.caption(
    "Click anywhere on the highlighted tunnel alignment. The system "
    "back-derives chainage, ring ID, and a coarse position zone. "
    "Picking visually is more reliable than typing a ring number."
)

# Re-render the map with the previously-picked chainage if any
prev_pick = st.session_state.ingest_picked_location
prev_chainage = (
    prev_pick["chainage_m"]
    if prev_pick and prev_pick.get("tunnel_id") == picked_tunnel_id
    else None
)

m = build_ingest_map(picked_tunnel_id, selected_chainage=prev_chainage)
map_state = st_folium(
    m,
    width=None,
    height=450,
    returned_objects=["last_clicked"],
    key=f"ingest_map_{picked_tunnel_id}",
)

# Resolve click → tunnel location
last_click = map_state.get("last_clicked") if map_state else None
if last_click:
    resolved = click_to_tunnel_location(
        last_click["lat"], last_click["lng"],
        candidate_tunnel_ids=[picked_tunnel_id],
    )
    if resolved is None:
        st.warning(
            "Click was too far from the tunnel alignment to project "
            "(>500 m). Click closer to the highlighted line."
        )
    else:
        # Add position from offset
        resolved["position"] = position_from_offset(
            resolved["perpendicular_offset_m"]
        )
        st.session_state.ingest_picked_location = resolved
        prev_pick = resolved

# Show the resolved location
if prev_pick:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Tunnel", prev_pick["tunnel_label"])
    with col2:
        st.metric("Chainage", f"K{prev_pick['chainage_m']:.0f} m")
    with col3:
        st.metric("Ring", str(prev_pick["ring_id"]))
    with col4:
        st.metric("Offset from CL",
                  f"{prev_pick['perpendicular_offset_m']:.0f} m")
    if st.button("Clear picked location", type="secondary"):
        st.session_state.ingest_picked_location = None
        st.rerun()
else:
    st.info(
        "No location picked yet. Click on the highlighted tunnel "
        "alignment above to set chainage and ring ID automatically. "
        "(You can still type them manually below if you prefer.)"
    )

st.divider()

# -----------------------------------------------------------------------------
# Input route selector
# -----------------------------------------------------------------------------
input_route = st.radio(
    "Input source",
    options=["Image (PNG / JPG / JPEG)", "Text (PDF / DOCX / TXT)"],
    horizontal=True,
)

extraction_route = st.radio(
    "Extraction method",
    options=[
        "Manual entry — I'll type the details myself",
        "Heuristic stub — let the app pre-fill what it can",
    ],
    help=(
        "The heuristic stub is a clearly-labelled placeholder for an "
        "upstream ML pipeline. It uses filename keywords and text "
        "regex — fine for a demo, not for production."
    ),
)

st.divider()


# -----------------------------------------------------------------------------
# Helpers — common form rendering
# -----------------------------------------------------------------------------
def _resolve_default_ring(picked: Optional[Dict]) -> str:
    return str(picked["ring_id"]) if picked else ""


def _resolve_default_chainage(picked: Optional[Dict]) -> float:
    return float(picked["chainage_m"]) if picked else 0.0


def _resolve_default_position(picked: Optional[Dict]) -> str:
    if not picked:
        return POSITION_OPTIONS[0]
    pos = picked.get("position", "")
    # Map gis.py positions to the more granular options in the form
    if pos == "Crown":
        return "Crown"
    return POSITION_OPTIONS[0]


# -----------------------------------------------------------------------------
# Image upload route
# -----------------------------------------------------------------------------
if input_route.startswith("Image"):
    uploaded = st.file_uploader(
        "Upload an inspection photo",
        type=["png", "jpg", "jpeg"],
        help="A single image of the defect, in any common format.",
    )

    prefilled_defect_type = "Unclassified"
    if uploaded is not None:
        st.image(uploaded, caption=uploaded.name, width=480)

        if extraction_route.startswith("Heuristic"):
            prefilled_defect_type = heuristic_defect_type_from_filename(
                uploaded.name
            )
            if prefilled_defect_type != "Unclassified":
                st.info(
                    f"Filename heuristic suggests **{prefilled_defect_type}** "
                    f"(based on keyword in `{uploaded.name}`). Adjust below "
                    f"if needed."
                )
            else:
                st.warning(
                    "No defect-type keyword found in filename. "
                    "Please pick the type below."
                )

        with st.form("image_ingest_form"):
            col1, col2 = st.columns(2)
            with col1:
                defect_type = st.selectbox(
                    "Defect type",
                    options=DEFECT_TYPE_OPTIONS,
                    index=DEFECT_TYPE_OPTIONS.index(prefilled_defect_type)
                    if prefilled_defect_type in DEFECT_TYPE_OPTIONS else 0,
                )
                ring_id = st.text_input(
                    "Ring ID",
                    value=_resolve_default_ring(prev_pick),
                    help="Auto-filled from the map click. Override here if needed.",
                )
                chainage_m = st.number_input(
                    "Chainage (m)",
                    min_value=0.0, step=1.0,
                    value=_resolve_default_chainage(prev_pick),
                )
            with col2:
                position_default_idx = (
                    POSITION_OPTIONS.index(_resolve_default_position(prev_pick))
                    if _resolve_default_position(prev_pick) in POSITION_OPTIONS
                    else 0
                )
                position = st.selectbox(
                    "Position", options=POSITION_OPTIONS,
                    index=position_default_idx,
                )
                priority = st.selectbox(
                    "Priority", options=PRIORITY_OPTIONS, index=1
                )
                description = st.text_input(
                    "Short description",
                    value=f"{defect_type} observed in inspection photo"
                    if defect_type else "",
                )

            with st.expander("Optional — quantitative measurements"):
                colm1, colm2, colm3 = st.columns(3)
                with colm1:
                    crack_width = st.number_input(
                        "Crack width (mm)", min_value=0.0, step=0.1, value=0.0
                    )
                with colm2:
                    spall_depth = st.number_input(
                        "Spall depth (mm)", min_value=0.0, step=1.0, value=0.0
                    )
                with colm3:
                    area_cm2 = st.number_input(
                        "Affected area (cm²)", min_value=0.0, step=1.0, value=0.0
                    )

            submitted = st.form_submit_button(
                "Register defect", type="primary"
            )

        if submitted:
            measurements: Dict = {}
            if crack_width > 0:
                measurements["crack_width_mm"] = crack_width
            if spall_depth > 0:
                measurements["spall_depth_mm"] = spall_depth
            if area_cm2 > 0:
                measurements["area_cm2"] = area_cm2

            modalities = ["RGB"]
            if measurements:
                modalities.append("RGBD")

            new_id = build_ingested_defect_id(
                ring_id=ring_id,
                defect_type=defect_type,
                sequence_number=len(st.session_state.ingested_defects) + 1,
            )
            defect = build_defect_dict(
                defect_id=new_id,
                defect_type=defect_type,
                description=description or f"{defect_type} from {uploaded.name}",
                ring_id=ring_id or "Unknown",
                chainage_m=chainage_m,
                position=position,
                priority=priority,
                evidence_modalities=modalities,
                source_filename=uploaded.name,
                source_kind="image",
                measurements=measurements,
            )
            # Tag with tunnel_id so map markers render correctly
            defect["tunnel_id"] = picked_tunnel_id

            st.session_state.ingested_defects.append(defect)
            st.session_state.defects.append(defect)
            st.session_state.selected_defect_id = new_id

            st.success(
                f"Registered **{new_id}** on **{picked_tunnel['label']}**. "
                f"Open **Defect Detail** in the sidebar to view the FMEA "
                f"chain and prescribed intervention."
            )

# -----------------------------------------------------------------------------
# Text upload route
# -----------------------------------------------------------------------------
else:
    uploaded = st.file_uploader(
        "Upload an inspection report",
        type=["pdf", "docx", "txt"],
    )

    extracted_text = ""
    prefilled = {
        "ring_id": _resolve_default_ring(prev_pick),
        "chainage_m": _resolve_default_chainage(prev_pick),
        "crack_width_mm": 0.0,
        "spall_depth_mm": 0.0,
        "defect_type_guess": "Unclassified",
    }

    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        extracted_text = extract_text_from_upload(file_bytes, uploaded.name)

        if not extracted_text:
            st.warning(
                f"Could not extract text from `{uploaded.name}`. "
                f"You can still register the defect manually below — "
                f"the file will be retained as the source reference."
            )
        else:
            with st.expander("Extracted text (first 1500 characters)",
                             expanded=False):
                st.code(extracted_text[:1500] +
                        ("..." if len(extracted_text) > 1500 else ""))

            if extraction_route.startswith("Heuristic"):
                heur = heuristic_fields_from_text(extracted_text)

                # Cross-check: if both the map click and the regex found a
                # ring, surface any disagreement.
                heur_ring = heur["ring_id"]
                map_ring = prev_pick["ring_id"] if prev_pick else None
                if heur_ring and map_ring and str(heur_ring) != str(map_ring):
                    st.warning(
                        f"⚠ **Cross-check disagreement.** The text extractor "
                        f"found Ring **{heur_ring}** in the report, but the "
                        f"map click resolved to Ring **{map_ring}**. Pick "
                        f"the correct value below before submitting — they "
                        f"shouldn't disagree."
                    )

                # Map click takes precedence; regex fills only what's missing
                if not prefilled["ring_id"] and heur_ring:
                    prefilled["ring_id"] = heur_ring
                if not prefilled["chainage_m"] and heur["chainage_m"]:
                    prefilled["chainage_m"] = heur["chainage_m"]
                prefilled["crack_width_mm"] = heur["crack_width_mm"] or 0.0
                prefilled["spall_depth_mm"] = heur["spall_depth_mm"] or 0.0
                if heur["defect_type_guess"]:
                    prefilled["defect_type_guess"] = heur["defect_type_guess"]

                found = [k for k, v in heur.items() if v]
                if found:
                    st.info(
                        f"Heuristic extractor found: "
                        f"{', '.join(found)}. Review and adjust below."
                    )
                else:
                    st.warning(
                        "Heuristic extractor could not find ring, chainage, "
                        "or measurements. Please fill in manually."
                    )

        with st.form("text_ingest_form"):
            col1, col2 = st.columns(2)
            with col1:
                defect_type = st.selectbox(
                    "Defect type",
                    options=DEFECT_TYPE_OPTIONS,
                    index=DEFECT_TYPE_OPTIONS.index(prefilled["defect_type_guess"])
                    if prefilled["defect_type_guess"] in DEFECT_TYPE_OPTIONS else 0,
                )
                ring_id = st.text_input(
                    "Ring ID", value=str(prefilled["ring_id"])
                )
                chainage_m = st.number_input(
                    "Chainage (m)", min_value=0.0, step=1.0,
                    value=float(prefilled["chainage_m"] or 0.0),
                )
            with col2:
                position = st.selectbox(
                    "Position", options=POSITION_OPTIONS,
                    index=(
                        POSITION_OPTIONS.index(
                            _resolve_default_position(prev_pick)
                        )
                        if _resolve_default_position(prev_pick) in POSITION_OPTIONS
                        else 0
                    ),
                )
                priority = st.selectbox(
                    "Priority", options=PRIORITY_OPTIONS, index=1
                )
                description = st.text_input(
                    "Short description",
                    value=f"{defect_type} reported in {uploaded.name}",
                )

            with st.expander("Optional — quantitative measurements"):
                colm1, colm2, colm3 = st.columns(3)
                with colm1:
                    crack_width = st.number_input(
                        "Crack width (mm)", min_value=0.0, step=0.1,
                        value=float(prefilled["crack_width_mm"]),
                    )
                with colm2:
                    spall_depth = st.number_input(
                        "Spall depth (mm)", min_value=0.0, step=1.0,
                        value=float(prefilled["spall_depth_mm"]),
                    )
                with colm3:
                    area_cm2 = st.number_input(
                        "Affected area (cm²)", min_value=0.0, step=1.0,
                        value=0.0,
                    )

            submitted = st.form_submit_button(
                "Register defect", type="primary"
            )

        if submitted:
            measurements = {}
            if crack_width > 0:
                measurements["crack_width_mm"] = crack_width
            if spall_depth > 0:
                measurements["spall_depth_mm"] = spall_depth
            if area_cm2 > 0:
                measurements["area_cm2"] = area_cm2

            modalities = ["InspectionReport"]
            if measurements:
                modalities.append("RGBD")

            new_id = build_ingested_defect_id(
                ring_id=ring_id,
                defect_type=defect_type,
                sequence_number=len(st.session_state.ingested_defects) + 1,
            )
            defect = build_defect_dict(
                defect_id=new_id,
                defect_type=defect_type,
                description=description or f"{defect_type} from {uploaded.name}",
                ring_id=ring_id or "Unknown",
                chainage_m=chainage_m,
                position=position,
                priority=priority,
                evidence_modalities=modalities,
                source_filename=uploaded.name,
                source_kind="text",
                measurements=measurements,
            )
            defect["tunnel_id"] = picked_tunnel_id

            st.session_state.ingested_defects.append(defect)
            st.session_state.defects.append(defect)
            st.session_state.selected_defect_id = new_id

            st.success(
                f"Registered **{new_id}** on **{picked_tunnel['label']}**. "
                f"Open **Defect Detail** in the sidebar to view the FMEA "
                f"chain and prescribed intervention."
            )

# -----------------------------------------------------------------------------
# List of defects ingested in this session
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Defects registered in this session")

if not st.session_state.ingested_defects:
    st.info(
        "No defects ingested yet. Upload a file above to register one. "
        "Defects from the ontology are visible on the **Defect Register** page."
    )
else:
    for d in reversed(st.session_state.ingested_defects):
        st.markdown(
            f"- **{d['defect_id']}** · {d['defect_type']} · "
            f"{d.get('tunnel_id', '?')} · Ring {d['ring_id']} · "
            f"source: `{d['source_filename']}` ({d['source_kind']})"
        )
