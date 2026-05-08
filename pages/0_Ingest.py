"""
Ingest — page 0
===============

Single-modality entry point. Operators can register a defect from:
    - an inspection image (PNG/JPG/JPEG), or
    - an inspection report (PDF/DOCX/TXT)

For each input route the user can pick:
    - Manual entry: type the defect type and measurements themselves.
    - Heuristic stub: filename + simple text rules pre-fill what they can,
      labelled as a demo placeholder for an upstream ML pipeline.

This page exists to make the app match operator reality — most defects
are first reported with one photo or a short text note, not with a
co-located four-modality survey. Multimodal fusion is then framed as
an enhancement, not a prerequisite.
"""

import streamlit as st
from datetime import date

from utils.ontology_loader import load_ontology, load_defects
from utils.styling import apply_custom_css
from utils.ingest import (
    DEFECT_TYPE_OPTIONS, PRIORITY_OPTIONS, POSITION_OPTIONS,
    extract_text_from_upload, heuristic_defect_type_from_filename,
    heuristic_fields_from_text, build_defect_dict,
)

st.set_page_config(page_title="Ingest", layout="wide")
apply_custom_css()

if "graph" not in st.session_state:
    st.session_state.graph = load_ontology()
    st.session_state.defects = load_defects(st.session_state.graph)

if "ingested_defects" not in st.session_state:
    st.session_state.ingested_defects = []

st.title("Ingest a defect")
st.caption(
    "Register a defect from a single inspection photo or a written "
    "inspection report. Multi-modal data is supported on the **CV → COBie "
    "Bridge** page; this page is for the common case of a single source."
)

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

        # ---- Form for the rest of the fields ----
        with st.form("image_ingest_form"):
            col1, col2 = st.columns(2)
            with col1:
                defect_type = st.selectbox(
                    "Defect type",
                    options=DEFECT_TYPE_OPTIONS,
                    index=DEFECT_TYPE_OPTIONS.index(prefilled_defect_type)
                    if prefilled_defect_type in DEFECT_TYPE_OPTIONS else 0,
                )
                ring_id = st.text_input("Ring ID", value="")
                chainage_m = st.number_input(
                    "Chainage (m)", min_value=0.0, step=1.0, value=0.0
                )
            with col2:
                position = st.selectbox("Position", options=POSITION_OPTIONS)
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
            measurements = {}
            if crack_width > 0:
                measurements["crack_width_mm"] = crack_width
            if spall_depth > 0:
                measurements["spall_depth_mm"] = spall_depth
            if area_cm2 > 0:
                measurements["area_cm2"] = area_cm2

            # An RGB photo populates the qualitative defect level. If the
            # operator added quantitative measurements, we also credit
            # RGBD-equivalent evidence.
            modalities = ["RGB"]
            if measurements:
                modalities.append("RGBD")

            new_id = f"D-ING-{len(st.session_state.ingested_defects)+1:03d}"
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

            st.session_state.ingested_defects.append(defect)
            st.session_state.defects.append(defect)
            st.session_state.selected_defect_id = new_id

            st.success(
                f"Registered **{new_id}**. Open **Defect Detail** in the "
                f"sidebar to view the FMEA chain and prescribed intervention."
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
        "ring_id": "",
        "chainage_m": 0.0,
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
                st.code(extracted_text[:1500] + ("..." if len(extracted_text) > 1500 else ""))

            if extraction_route.startswith("Heuristic"):
                heur = heuristic_fields_from_text(extracted_text)
                prefilled["ring_id"] = heur["ring_id"] or ""
                prefilled["chainage_m"] = heur["chainage_m"] or 0.0
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

        # ---- Form ----
        with st.form("text_ingest_form"):
            col1, col2 = st.columns(2)
            with col1:
                defect_type = st.selectbox(
                    "Defect type",
                    options=DEFECT_TYPE_OPTIONS,
                    index=DEFECT_TYPE_OPTIONS.index(prefilled["defect_type_guess"])
                    if prefilled["defect_type_guess"] in DEFECT_TYPE_OPTIONS else 0,
                )
                ring_id = st.text_input("Ring ID", value=str(prefilled["ring_id"]))
                chainage_m = st.number_input(
                    "Chainage (m)", min_value=0.0, step=1.0,
                    value=float(prefilled["chainage_m"] or 0.0),
                )
            with col2:
                position = st.selectbox("Position", options=POSITION_OPTIONS)
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

            # A text report contributes at the qualitative defect level
            # via the inspector's classification. If quantitative
            # measurements are present, we credit the indicator level too.
            modalities = ["InspectionReport"]
            if measurements:
                modalities.append("RGBD")

            new_id = f"D-ING-{len(st.session_state.ingested_defects)+1:03d}"
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

            st.session_state.ingested_defects.append(defect)
            st.session_state.defects.append(defect)
            st.session_state.selected_defect_id = new_id

            st.success(
                f"Registered **{new_id}**. Open **Defect Detail** in the "
                f"sidebar to view the FMEA chain and prescribed intervention."
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
            f"Ring {d['ring_id']} · "
            f"source: `{d['source_filename']}` "
            f"({d['source_kind']})"
        )
