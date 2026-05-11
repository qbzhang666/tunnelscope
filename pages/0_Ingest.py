"""
Ingest — page 0
===============

Single-modality entry point. Operators register a defect from:
    - an inspection image (PNG/JPG/JPEG), or
    - an inspection report (PDF/DOCX/TXT)

REVISED (Rev 6b):
- FORM-FIRST FLOW. Operators upload a source, choose extraction method,
  fill in (or accept) ring/chainage values, then a CONFIRMATION map
  appears below the form showing where their entered location projects
  to on the alignment. The map is now an output (verification), not an
  input (selection).
- Heuristic stub still extracts ring/chainage from filename or text and
  pre-fills the form.
- Newly-registered defects are appended to st.session_state.defects so
  they appear immediately on the Defect Register's map and table.
"""

from typing import Dict

import streamlit as st

from utils.ontology_loader import load_ontology, load_defects
from utils.styling import apply_custom_css
from utils.ingest import (
    DEFECT_TYPE_OPTIONS, PRIORITY_OPTIONS, POSITION_OPTIONS,
    extract_text_from_upload, heuristic_defect_type_from_filename,
    heuristic_fields_from_text, build_defect_dict,
    build_ingested_defect_id,
)
from utils.gis import list_tunnels, build_confirmation_map

st.set_page_config(page_title="Ingest", layout="wide")
apply_custom_css()

if "graph" not in st.session_state:
    st.session_state.graph = load_ontology()
    st.session_state.defects = load_defects(st.session_state.graph)

if "ingested_defects" not in st.session_state:
    st.session_state.ingested_defects = []


st.title("Ingest a defect")
st.caption(
    "Register a defect from a single inspection photo or written "
    "inspection report. After you've entered ring and chainage, the "
    "map below the form will show where the location projects to so "
    "you can verify before submitting."
)

# -----------------------------------------------------------------------------
# Session counter — visible reminder of what's been registered already,
# helps prevent the accidental-double-click problem
# -----------------------------------------------------------------------------
_ingested = st.session_state.get("ingested_defects", [])
if _ingested:
    _latest = _ingested[-3:]
    _latest_summary = ", ".join(
        f"`{d['defect_id']}`" for d in reversed(_latest)
    )
    st.success(
        f"📋 **Defects already registered this session: {len(_ingested)}** — "
        f"latest: {_latest_summary}. "
        f"If your most recent submission appears here, the registration "
        f"succeeded — no need to click 'Register defect' again."
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

st.divider()

# -----------------------------------------------------------------------------
# Input route + extraction method
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
        "Local LVM (Ollama / Qwen) — manual feedback loop",
    ],
    help=(
        "Three options.  **Manual** is exactly what it sounds like.  "
        "**Heuristic** uses filename keywords and text regex — fine for "
        "a demo, not for production.  **Local LVM** sends the uploaded "
        "image or text to a vision-capable model running on YOUR machine "
        "via Ollama (e.g. Qwen2.5-VL).  The model's response is shown so "
        "you can read it and manually copy useful fields into the form "
        "below — the feedback loop is intentionally manual at this stage."
    ),
)

st.divider()

# -----------------------------------------------------------------------------
# Local LVM panel — only shown when that route is selected
# -----------------------------------------------------------------------------
USE_LOCAL_LVM = extraction_route.startswith("Local LVM")

if USE_LOCAL_LVM:
    from utils.local_lvm import (
        check_ollama_health, list_local_models,
        DEFAULT_ENDPOINT, DEFAULT_MODEL,
        DEFAULT_IMAGE_PROMPT, DEFAULT_TEXT_PROMPT,
    )

    st.info(
        "**Local LVM mode — how this works.**  Your image or report is "
        "sent to a model server running on **your own machine** (Ollama, "
        "by default at `http://localhost:11434`).  Nothing leaves your "
        "machine; this is not a cloud inference call.  The model's "
        "response appears below — read it, then manually type the "
        "relevant fields into the form.  This is deliberate: silently "
        "auto-parsing model output would create wrong metadata if the "
        "model hallucinated, so a human-in-the-loop confirmation step "
        "is required.  If Ollama is not running locally (e.g. on the "
        "Streamlit Cloud deployment), this mode will not work — fall "
        "back to Manual or Heuristic."
    )

    with st.expander("Local model configuration", expanded=True):
        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1:
            ollama_endpoint = st.text_input(
                "Ollama endpoint",
                value=st.session_state.get(
                    "ollama_endpoint", DEFAULT_ENDPOINT
                ),
                help="Default is the standard local Ollama address. "
                     "Change only if you've configured Ollama on a "
                     "different host/port.",
            )
            st.session_state.ollama_endpoint = ollama_endpoint
        with col_cfg2:
            # Try to populate the model selector from the live server
            health_ok, health_msg = check_ollama_health(ollama_endpoint)
            if health_ok:
                models_available = list_local_models(ollama_endpoint)
                if not models_available:
                    models_available = [DEFAULT_MODEL]
                ollama_model = st.selectbox(
                    "Model",
                    options=models_available,
                    index=(models_available.index(DEFAULT_MODEL)
                           if DEFAULT_MODEL in models_available else 0),
                    help="Picked from the models installed in your "
                         "local Ollama. For images, pick a "
                         "vision-capable model (Qwen2.5-VL, LLaVA, "
                         "Llama 3.2 Vision).",
                )
            else:
                ollama_model = st.text_input(
                    "Model name (server unreachable — type manually)",
                    value=DEFAULT_MODEL,
                )
            st.session_state.ollama_model = ollama_model

        if health_ok:
            st.success(f"✓ {health_msg}")
        else:
            st.warning(f"⚠ {health_msg}")

    st.divider()


# -----------------------------------------------------------------------------
# Helpers — common rendering
# -----------------------------------------------------------------------------
def _is_likely_duplicate(
    tunnel_id: str,
    defect_type: str,
    ring_id: str,
    chainage_m: float,
    source_filename: str,
) -> bool:
    """
    Detect if the same defect was just registered. Looks at the most
    recently-ingested defect this session and compares the salient
    fields. If they all match, the operator probably double-clicked
    Register and we should refuse the second submission.
    """
    recent = st.session_state.get("ingested_defects", [])
    if not recent:
        return False
    last = recent[-1]
    return all([
        last.get("tunnel_id") == tunnel_id,
        last.get("defect_type") == defect_type,
        str(last.get("ring_id", "")) == str(ring_id),
        abs(float(last.get("chainage_m", 0)) - float(chainage_m)) < 0.5,
        last.get("source_filename") == source_filename,
    ])


def _render_confirmation_map(
    tunnel_id: str,
    ring_id: str,
    chainage_m: float,
):
    """Render the post-form confirmation map below the form."""
    if chainage_m <= 0 and not ring_id:
        st.info(
            "Enter a chainage or ring ID above and a confirmation map "
            "will appear here showing where the location projects to."
        )
        return

    # Resolve chainage from ring if only ring is provided
    effective_chainage = chainage_m
    if effective_chainage <= 0 and ring_id:
        try:
            ring_int = int(ring_id)
            ring_length = picked_tunnel.get("ring_length_m", 1.6)
            effective_chainage = ring_int * ring_length
        except (ValueError, TypeError):
            pass

    if effective_chainage <= 0:
        st.info(
            "Could not resolve a chainage from the entered values. "
            "Enter chainage in metres for a confirmation map."
        )
        return

    # Sanity: warn if chainage is outside tunnel length
    tunnel_length = picked_tunnel.get("length_m", 0)
    if effective_chainage > tunnel_length:
        st.warning(
            f"⚠ Entered chainage K{effective_chainage:.0f}m exceeds "
            f"{picked_tunnel['label']}'s length of {tunnel_length} m. "
            f"The marker will be placed at the eastern portal — "
            f"check your entered values."
        )

    st.subheader("Confirmation — does this look right?")
    st.caption(
        f"Marker shows where Ring {ring_id or '—'} / "
        f"K{effective_chainage:.0f}m projects on {picked_tunnel['label']}. "
        f"If the marker isn't where the defect actually is, correct the "
        f"values above before submitting."
    )

    confirm_map = build_confirmation_map(
        tunnel_id=tunnel_id,
        chainage_m=effective_chainage,
        ring_id=ring_id if ring_id else None,
        height=380,
    )

    # Render via folium's HTML so we don't need st_folium for this
    # output-only map. Avoids re-render lag from click events that
    # we don't need here.
    from streamlit.components.v1 import html as components_html
    components_html(confirm_map._repr_html_(), height=400)


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
        # Show the image alongside the form
        col_img, col_form = st.columns([1, 2])
        with col_img:
            st.image(uploaded, caption=uploaded.name, use_container_width=True)

        # ---- Local LVM inference (image route) ----
        if USE_LOCAL_LVM:
            with col_form:
                st.markdown("**Local LVM inference**")
                custom_prompt = st.text_area(
                    "Prompt",
                    value=st.session_state.get(
                        "lvm_image_prompt", DEFAULT_IMAGE_PROMPT
                    ),
                    height=180,
                    help="Edit if you want different output formatting. "
                         "Defaults are tuned for tunnel inspection.",
                )
                st.session_state.lvm_image_prompt = custom_prompt

                if st.button("Run inference on this image",
                             key="run_lvm_image"):
                    from utils.local_lvm import run_image_inference
                    with st.spinner(
                        f"Running {st.session_state.ollama_model} "
                        f"on local machine — this may take 30–120 s "
                        f"depending on model size and CPU/GPU…"
                    ):
                        result = run_image_inference(
                            image_bytes=uploaded.getvalue(),
                            prompt=custom_prompt,
                            model=st.session_state.ollama_model,
                            endpoint=st.session_state.ollama_endpoint,
                        )
                    st.session_state.lvm_image_result = result

                # Show last inference result if any
                last_result = st.session_state.get("lvm_image_result")
                if last_result:
                    if last_result["ok"]:
                        st.success("Inference complete — read the model "
                                   "output below and copy relevant fields "
                                   "into the form. Do NOT trust verbatim.")
                        st.markdown("**Model output:**")
                        st.markdown(
                            f"> {last_result['text']}".replace("\n", "\n> ")
                        )
                    else:
                        st.error(
                            f"Inference failed: {last_result.get('error', 'unknown')}"
                        )

        if extraction_route.startswith("Heuristic"):
            prefilled_defect_type = heuristic_defect_type_from_filename(
                uploaded.name
            )
            with col_form:
                if prefilled_defect_type != "Unclassified":
                    st.info(
                        f"Filename heuristic suggests "
                        f"**{prefilled_defect_type}** based on `{uploaded.name}`. "
                        f"Adjust below if needed."
                    )
                else:
                    st.warning(
                        "No defect-type keyword found in filename. "
                        "Please pick the type below."
                    )

        with col_form:
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
                        value="",
                        help="Type the ring ID where the defect is. "
                             "If you only know the chainage, leave this "
                             "blank and fill chainage instead.",
                    )
                    chainage_m = st.number_input(
                        "Chainage (m)",
                        min_value=0.0, step=1.0, value=0.0,
                        help="Distance along the tunnel from the western portal.",
                    )
                with col2:
                    position = st.selectbox(
                        "Position", options=POSITION_OPTIONS,
                    )
                    priority = st.selectbox(
                        "Priority", options=PRIORITY_OPTIONS, index=1
                    )
                    description = st.text_input(
                        "Short description",
                        value=f"{defect_type} observed in inspection photo",
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

                preview_clicked = st.form_submit_button(
                    "Preview on map", help="Render the confirmation map below."
                )
                submitted = st.form_submit_button(
                    "Register defect", type="primary"
                )

        # Confirmation map below the form (full width)
        st.divider()
        _render_confirmation_map(picked_tunnel_id, ring_id, chainage_m)

        if submitted:
            # Duplicate-click guard — refuse if the same fields were
            # just submitted (catches the accidental-double-click case).
            if _is_likely_duplicate(
                tunnel_id=picked_tunnel_id,
                defect_type=defect_type,
                ring_id=ring_id,
                chainage_m=chainage_m,
                source_filename=uploaded.name,
            ):
                last_id = st.session_state.ingested_defects[-1]["defect_id"]
                st.warning(
                    f"⚠ This looks like a duplicate of "
                    f"**{last_id}** that was just registered "
                    f"({uploaded.name} · Ring {ring_id} · K{chainage_m:.0f}m). "
                    f"If you really want to register this as a separate "
                    f"defect, change at least one field (ring, chainage, "
                    f"description, etc.) before clicking Register again."
                )
                st.stop()

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
            defect["tunnel_id"] = picked_tunnel_id

            st.session_state.ingested_defects.append(defect)
            st.session_state.defects.append(defect)
            st.session_state.selected_defect_id = new_id

            st.success(
                f"Registered **{new_id}** on **{picked_tunnel['label']}**. "
                f"Open **Defect Detail** in the sidebar for the FMEA chain, "
                f"or **Defect Register** to see it on the overview map."
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
                st.code(extracted_text[:1500] +
                        ("..." if len(extracted_text) > 1500 else ""))

            # ---- Local LVM inference (text route) ----
            if USE_LOCAL_LVM:
                st.markdown("**Local LVM inference**")
                custom_text_prompt = st.text_area(
                    "Prompt template (use `{text}` where the "
                    "extracted text should be substituted)",
                    value=st.session_state.get(
                        "lvm_text_prompt", DEFAULT_TEXT_PROMPT
                    ),
                    height=200,
                    key="lvm_text_prompt_area",
                )
                st.session_state.lvm_text_prompt = custom_text_prompt

                if st.button("Run inference on this report",
                             key="run_lvm_text"):
                    from utils.local_lvm import run_text_inference
                    with st.spinner(
                        f"Running {st.session_state.ollama_model} "
                        f"on local machine…"
                    ):
                        result = run_text_inference(
                            text=extracted_text,
                            prompt_template=custom_text_prompt,
                            model=st.session_state.ollama_model,
                            endpoint=st.session_state.ollama_endpoint,
                        )
                    st.session_state.lvm_text_result = result

                last_result = st.session_state.get("lvm_text_result")
                if last_result:
                    if last_result["ok"]:
                        st.success("Inference complete — read the model "
                                   "output below and copy useful fields "
                                   "into the form. Do NOT trust verbatim.")
                        st.markdown("**Model output:**")
                        st.markdown(
                            f"> {last_result['text']}".replace("\n", "\n> ")
                        )
                    else:
                        st.error(
                            f"Inference failed: {last_result.get('error', 'unknown')}"
                        )

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

            preview_clicked = st.form_submit_button(
                "Preview on map", help="Render the confirmation map below."
            )
            submitted = st.form_submit_button(
                "Register defect", type="primary"
            )

        # Confirmation map below the form
        st.divider()
        _render_confirmation_map(picked_tunnel_id, ring_id, chainage_m)

        if submitted:
            # Duplicate-click guard — same logic as the image route.
            if _is_likely_duplicate(
                tunnel_id=picked_tunnel_id,
                defect_type=defect_type,
                ring_id=ring_id,
                chainage_m=chainage_m,
                source_filename=uploaded.name,
            ):
                last_id = st.session_state.ingested_defects[-1]["defect_id"]
                st.warning(
                    f"⚠ This looks like a duplicate of "
                    f"**{last_id}** that was just registered "
                    f"({uploaded.name} · Ring {ring_id} · K{chainage_m:.0f}m). "
                    f"If you really want to register this as a separate "
                    f"defect, change at least one field (ring, chainage, "
                    f"description, etc.) before clicking Register again."
                )
                st.stop()

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
                f"Open **Defect Detail** in the sidebar for the FMEA chain, "
                f"or **Defect Register** to see it on the overview map."
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
            f"K{d.get('chainage_m', 0):.0f}m · "
            f"source: `{d['source_filename']}` ({d['source_kind']})"
        )
