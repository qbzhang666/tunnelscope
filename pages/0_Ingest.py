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
from utils.explainers import render_plain_guide

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

render_plain_guide(
    "Add one defect from a photo or report. Check the pre-filled "
    "details, confirm the map location, press **Register defect** — it "
    "then joins the Defect Register like any survey finding."
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
        "🤖 AI auto-classify (local model) — recognise & fill the form",
        "☁️ Cloud VLM (Claude / OpenAI / Gemini) — no local model needed",
        "Local LVM (Ollama / Qwen) — raw output, manual copy",
    ],
    index=2,
    help=(
        "**Manual** — type everything yourself.  "
        "**Heuristic** — filename keywords / text regex (demo only).  "
        "**AI auto-classify (local)** — a model on YOUR machine (Ollama) "
        "reads the photo/report and pre-fills the form; nothing leaves "
        "your computer.  **Cloud VLM** — same, but via a hosted API "
        "(Anthropic / OpenAI / Google) for users without a local model; "
        "needs an API key and sends the image/report to that provider.  "
        "**Local LVM** — local model, raw output for manual copy."
    ),
)

st.divider()

# -----------------------------------------------------------------------------
# Local LVM panel — only shown when that route is selected
# -----------------------------------------------------------------------------
USE_AI_CLASSIFY = "local model" in extraction_route
USE_CLOUD_VLM = "Cloud VLM" in extraction_route
USE_LOCAL_LVM = extraction_route.startswith("Local LVM")
USE_LOCAL_MODEL = USE_AI_CLASSIFY or USE_LOCAL_LVM
_IS_IMAGE_ROUTE = input_route.startswith("Image")

if USE_LOCAL_MODEL:
    from utils.local_lvm import (
        check_ollama_health, list_local_models, list_vision_models,
        DEFAULT_ENDPOINT, DEFAULT_MODEL, DEFAULT_TEXT_CLASSIFY_MODEL,
        DEFAULT_IMAGE_PROMPT, DEFAULT_TEXT_PROMPT,
    )

    if USE_AI_CLASSIFY:
        st.info(
            f"**AI auto-classify — runs on YOUR machine.** The uploaded "
            f"{'photo' if _IS_IMAGE_ROUTE else 'report'} is sent to a "
            f"local Ollama model (default `http://localhost:11434`); "
            f"nothing leaves your computer. The model's best guess "
            f"**pre-fills the form** below — always review and correct it "
            f"before registering, since models can be wrong. Needs Ollama "
            f"running locally; on the cloud deployment, use Manual."
        )
    else:
        st.info(
            "**Local LVM mode.** Your image or report is sent to a model "
            "on your own machine (Ollama). The raw response appears below "
            "— read it and type the relevant fields into the form "
            "yourself. Nothing leaves your machine."
        )

    with st.expander("Local model configuration", expanded=True):
        col_cfg1, col_cfg2 = st.columns(2)
        with col_cfg1:
            ollama_endpoint = st.text_input(
                "Ollama endpoint",
                value=st.session_state.get("ollama_endpoint",
                                           DEFAULT_ENDPOINT),
                help="The standard local Ollama address. Change only if "
                     "you run Ollama on a different host/port.",
            )
            st.session_state.ollama_endpoint = ollama_endpoint
        with col_cfg2:
            health_ok, health_msg = check_ollama_health(ollama_endpoint)
            if health_ok:
                models_available = list_local_models(ollama_endpoint) or \
                    [DEFAULT_MODEL]
                vision_models = list_vision_models(ollama_endpoint)
                # Default to a vision model for photos, a text model for
                # reports — so the right kind of model is pre-selected.
                if _IS_IMAGE_ROUTE:
                    preferred = next(iter(vision_models), DEFAULT_MODEL)
                elif DEFAULT_TEXT_CLASSIFY_MODEL in models_available:
                    preferred = DEFAULT_TEXT_CLASSIFY_MODEL
                else:
                    preferred = models_available[0]
                ollama_model = st.selectbox(
                    "Model", options=models_available,
                    index=(models_available.index(preferred)
                           if preferred in models_available else 0),
                    help="For PHOTOS pick a vision model (name has 'vl', "
                         "'llava', 'vision'); for REPORTS any instruct "
                         "model works.",
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

        # Photo recognition needs a vision model; guide the pull if absent.
        if (USE_AI_CLASSIFY and _IS_IMAGE_ROUTE and health_ok
                and not list_vision_models(ollama_endpoint)):
            st.warning(
                "No vision-capable model is installed in your local "
                "Ollama, so **photo** recognition can't run yet. Pull one "
                "in a terminal, e.g.\n\n"
                "```\nollama pull qwen2.5vl:7b\n```\n"
                "(or `llava:7b`, `moondream`). Report (text) "
                "auto-classify already works with your text models."
            )

    st.divider()


# -----------------------------------------------------------------------------
# Cloud VLM panel — for users without a local model
# -----------------------------------------------------------------------------
if USE_CLOUD_VLM:
    from utils.cloud_vlm import PROVIDERS, DEFAULT_MODELS, KEY_ENV_NAMES, \
        api_key_from_env

    st.info(
        "**Cloud VLM mode.** The uploaded "
        f"{'photo' if _IS_IMAGE_ROUTE else 'report'} is sent to a hosted "
        "Vision-Language model to recognise the defect and pre-fill the "
        "form. Use this if you don't run a local model. **Note:** unlike "
        "the local options, the image/report **leaves your machine** for "
        "the chosen provider's API. Needs an API key; review every "
        "suggestion before registering."
    )

    with st.expander("Cloud provider & API key", expanded=True):
        ccol1, ccol2 = st.columns(2)
        with ccol1:
            cloud_provider = st.selectbox("Provider", options=PROVIDERS)
            st.session_state.cloud_provider = cloud_provider
        with ccol2:
            cloud_model = st.text_input(
                "Model",
                value=st.session_state.get(
                    f"cloud_model_{cloud_provider}",
                    DEFAULT_MODELS[cloud_provider]),
                help="Editable — point at a newer or cheaper model if you "
                     "like (e.g. a Haiku/Sonnet, gpt-4o-mini, "
                     "gemini-1.5-flash).",
            )
            st.session_state[f"cloud_model_{cloud_provider}"] = cloud_model
            st.session_state.cloud_model = cloud_model

        # Resolve a key: Streamlit secrets → environment → manual entry.
        secret_key = None
        for nm in KEY_ENV_NAMES[cloud_provider]:
            try:
                if nm in st.secrets:
                    secret_key = st.secrets[nm]
                    break
            except Exception:
                pass
        resolved = secret_key or api_key_from_env(cloud_provider)
        if resolved:
            st.success(
                "✓ API key found in "
                + ("Streamlit secrets" if secret_key else "the environment")
                + " — no need to paste it."
            )
            st.session_state.cloud_key = resolved
        else:
            cloud_key = st.text_input(
                f"{cloud_provider} API key",
                value=st.session_state.get(f"cloud_key_{cloud_provider}", ""),
                type="password",
                help="Held only for this session — never written to disk. "
                     "For a permanent setup add it to "
                     "`.streamlit/secrets.toml` (git-ignored) as "
                     f"`{KEY_ENV_NAMES[cloud_provider][0]} = \"...\"`.",
            )
            st.session_state[f"cloud_key_{cloud_provider}"] = cloud_key
            st.session_state.cloud_key = cloud_key

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

    # Form defaults, possibly overridden by heuristic or AI classification.
    prefill = {
        "defect_type": "Unclassified", "position": None,
        "priority": "MEDIUM", "description": None,
        "crack_width_mm": 0.0, "spall_depth_mm": 0.0, "area_cm2": 0.0,
    }

    if uploaded is not None:
        # Show the image alongside the form
        col_img, col_form = st.columns([1, 2])
        with col_img:
            st.image(uploaded, caption=uploaded.name, width="stretch")

        # ---- AI auto-classify (image route) — fills the form ----
        if USE_AI_CLASSIFY:
            with col_form:
                st.markdown("**🤖 AI defect recognition**")
                if st.button("Classify this photo with AI",
                             key="run_ai_image", type="primary"):
                    from utils.local_lvm import classify_defect_image
                    with st.spinner(
                        f"Running {st.session_state.ollama_model} on your "
                        f"machine — a photo can take 30–120 s on CPU…"
                    ):
                        res = classify_defect_image(
                            image_bytes=uploaded.getvalue(),
                            model=st.session_state.ollama_model,
                            endpoint=st.session_state.ollama_endpoint,
                        )
                    res["_file"] = uploaded.name
                    st.session_state.ai_image_result = res

                air = st.session_state.get("ai_image_result")
                if air and air.get("_file") == uploaded.name:
                    if air["ok"]:
                        f = air["fields"]
                        conf = f.get("confidence")
                        st.success(
                            "AI suggestion ready — the form below is "
                            "pre-filled. **Review and correct before "
                            "registering.**"
                            + (f"  ·  confidence {conf * 100:.0f}%"
                               if conf else "")
                        )
                        if f.get("reasoning"):
                            st.caption(f"Model reasoning: _{f['reasoning']}_")
                        prefill["defect_type"] = (f.get("defect_type")
                                                  or "Unclassified")
                        prefill["position"] = f.get("position")
                        prefill["priority"] = f.get("priority") or "MEDIUM"
                        prefill["crack_width_mm"] = f.get("crack_width_mm") or 0.0
                        prefill["spall_depth_mm"] = f.get("spall_depth_mm") or 0.0
                        prefill["area_cm2"] = f.get("area_cm2") or 0.0
                        prefill["description"] = (
                            f"{prefill['defect_type']} — AI-recognised from "
                            f"{uploaded.name}")
                        with st.expander("Raw model output"):
                            st.code(air.get("raw") or "", language="json")
                    else:
                        st.error(
                            f"AI classification failed: {air.get('error')}")
                        if air.get("raw"):
                            with st.expander("Raw model output"):
                                st.code(air["raw"])
                else:
                    st.caption(
                        "Press the button to let the local model read the "
                        "photo and pre-fill the form for your review."
                    )

        # ---- Cloud VLM auto-classify (image route) — fills the form ----
        if USE_CLOUD_VLM:
            with col_form:
                provider = st.session_state.get("cloud_provider", "")
                st.markdown(f"**☁️ Cloud VLM — {provider}**")
                if st.button("Classify this photo (cloud)",
                             key="run_cloud_image", type="primary"):
                    from utils.cloud_vlm import classify_defect_image_cloud
                    with st.spinner(
                        f"Sending the photo to {provider} "
                        f"({st.session_state.get('cloud_model')})…"
                    ):
                        res = classify_defect_image_cloud(
                            image_bytes=uploaded.getvalue(),
                            provider=provider,
                            api_key=st.session_state.get("cloud_key", ""),
                            model=st.session_state.get("cloud_model"),
                        )
                    res["_file"] = uploaded.name
                    st.session_state.cloud_image_result = res

                air = st.session_state.get("cloud_image_result")
                if air and air.get("_file") == uploaded.name:
                    if air["ok"]:
                        f = air["fields"]
                        conf = f.get("confidence")
                        st.success(
                            "Cloud suggestion ready — the form below is "
                            "pre-filled. **Review and correct before "
                            "registering.**"
                            + (f"  ·  confidence {conf * 100:.0f}%"
                               if conf else "")
                        )
                        if f.get("reasoning"):
                            st.caption(f"Model reasoning: _{f['reasoning']}_")
                        prefill["defect_type"] = (f.get("defect_type")
                                                  or "Unclassified")
                        prefill["position"] = f.get("position")
                        prefill["priority"] = f.get("priority") or "MEDIUM"
                        prefill["crack_width_mm"] = f.get("crack_width_mm") or 0.0
                        prefill["spall_depth_mm"] = f.get("spall_depth_mm") or 0.0
                        prefill["area_cm2"] = f.get("area_cm2") or 0.0
                        prefill["description"] = (
                            f"{prefill['defect_type']} — AI-recognised from "
                            f"{uploaded.name}")
                        with st.expander("Raw model output"):
                            st.code(air.get("raw") or "", language="json")
                    else:
                        st.error(
                            f"Cloud classification failed: {air.get('error')}")
                        if air.get("raw"):
                            with st.expander("Raw model output"):
                                st.code(air["raw"])

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
            prefill["defect_type"] = heuristic_defect_type_from_filename(
                uploaded.name
            )
            with col_form:
                if prefill["defect_type"] != "Unclassified":
                    st.info(
                        f"Filename heuristic suggests "
                        f"**{prefill['defect_type']}** based on "
                        f"`{uploaded.name}`. Adjust below if needed."
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
                        index=DEFECT_TYPE_OPTIONS.index(prefill["defect_type"])
                        if prefill["defect_type"] in DEFECT_TYPE_OPTIONS else 0,
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
                        index=POSITION_OPTIONS.index(prefill["position"])
                        if prefill["position"] in POSITION_OPTIONS else 0,
                    )
                    priority = st.selectbox(
                        "Priority", options=PRIORITY_OPTIONS,
                        index=PRIORITY_OPTIONS.index(prefill["priority"])
                        if prefill["priority"] in PRIORITY_OPTIONS else 1,
                    )
                    description = st.text_input(
                        "Short description",
                        value=prefill["description"]
                        or f"{defect_type} observed in inspection photo",
                    )

                with st.expander("Optional — quantitative measurements"):
                    colm1, colm2, colm3 = st.columns(3)
                    with colm1:
                        crack_width = st.number_input(
                            "Crack width (mm)", min_value=0.0, step=0.1,
                            value=float(prefill["crack_width_mm"]),
                        )
                    with colm2:
                        spall_depth = st.number_input(
                            "Spall depth (mm)", min_value=0.0, step=1.0,
                            value=float(prefill["spall_depth_mm"]),
                        )
                    with colm3:
                        area_cm2 = st.number_input(
                            "Affected area (cm²)", min_value=0.0, step=1.0,
                            value=float(prefill["area_cm2"]),
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
        "position": None,
        "priority": "MEDIUM",
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

            # ---- AI auto-classify (text route) — fills the form ----
            if USE_AI_CLASSIFY:
                st.markdown("**🤖 AI field extraction**")
                if st.button("Extract fields with AI", key="run_ai_text",
                             type="primary"):
                    from utils.local_lvm import classify_defect_text
                    with st.spinner(
                        f"Running {st.session_state.ollama_model} on your "
                        f"machine…"
                    ):
                        res = classify_defect_text(
                            text=extracted_text,
                            model=st.session_state.ollama_model,
                            endpoint=st.session_state.ollama_endpoint,
                        )
                    res["_file"] = uploaded.name
                    st.session_state.ai_text_result = res

                air = st.session_state.get("ai_text_result")
                if air and air.get("_file") == uploaded.name:
                    if air["ok"]:
                        f = air["fields"]
                        conf = f.get("confidence")
                        st.success(
                            "AI suggestion ready — the form below is "
                            "pre-filled. **Review and correct before "
                            "registering.**"
                            + (f"  ·  confidence {conf * 100:.0f}%"
                               if conf else "")
                        )
                        if f.get("reasoning"):
                            st.caption(f"Model reasoning: _{f['reasoning']}_")
                        if f.get("defect_type"):
                            prefilled["defect_type_guess"] = f["defect_type"]
                        if f.get("ring_id") is not None:
                            prefilled["ring_id"] = str(f["ring_id"])
                        prefilled["chainage_m"] = f.get("chainage_m") or 0.0
                        prefilled["crack_width_mm"] = f.get("crack_width_mm") or 0.0
                        prefilled["spall_depth_mm"] = f.get("spall_depth_mm") or 0.0
                        prefilled["position"] = f.get("position")
                        prefilled["priority"] = f.get("priority") or "MEDIUM"
                        with st.expander("Raw model output"):
                            st.code(air.get("raw") or "", language="json")
                    else:
                        st.error(
                            f"AI extraction failed: {air.get('error')}")
                        if air.get("raw"):
                            with st.expander("Raw model output"):
                                st.code(air["raw"])

            # ---- Cloud VLM field extraction (text route) ----
            if USE_CLOUD_VLM:
                provider = st.session_state.get("cloud_provider", "")
                st.markdown(f"**☁️ Cloud VLM — {provider}**")
                if st.button("Extract fields (cloud)", key="run_cloud_text",
                             type="primary"):
                    from utils.cloud_vlm import classify_defect_text_cloud
                    with st.spinner(f"Sending the report to {provider}…"):
                        res = classify_defect_text_cloud(
                            text=extracted_text,
                            provider=provider,
                            api_key=st.session_state.get("cloud_key", ""),
                            model=st.session_state.get("cloud_model"),
                        )
                    res["_file"] = uploaded.name
                    st.session_state.cloud_text_result = res

                air = st.session_state.get("cloud_text_result")
                if air and air.get("_file") == uploaded.name:
                    if air["ok"]:
                        f = air["fields"]
                        conf = f.get("confidence")
                        st.success(
                            "Cloud suggestion ready — the form below is "
                            "pre-filled. **Review and correct before "
                            "registering.**"
                            + (f"  ·  confidence {conf * 100:.0f}%"
                               if conf else "")
                        )
                        if f.get("reasoning"):
                            st.caption(f"Model reasoning: _{f['reasoning']}_")
                        if f.get("defect_type"):
                            prefilled["defect_type_guess"] = f["defect_type"]
                        if f.get("ring_id") is not None:
                            prefilled["ring_id"] = str(f["ring_id"])
                        prefilled["chainage_m"] = f.get("chainage_m") or 0.0
                        prefilled["crack_width_mm"] = f.get("crack_width_mm") or 0.0
                        prefilled["spall_depth_mm"] = f.get("spall_depth_mm") or 0.0
                        prefilled["position"] = f.get("position")
                        prefilled["priority"] = f.get("priority") or "MEDIUM"
                        with st.expander("Raw model output"):
                            st.code(air.get("raw") or "", language="json")
                    else:
                        st.error(
                            f"Cloud extraction failed: {air.get('error')}")
                        if air.get("raw"):
                            with st.expander("Raw model output"):
                                st.code(air["raw"])

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
                    index=POSITION_OPTIONS.index(prefilled["position"])
                    if prefilled["position"] in POSITION_OPTIONS else 0,
                )
                priority = st.selectbox(
                    "Priority", options=PRIORITY_OPTIONS,
                    index=PRIORITY_OPTIONS.index(prefilled["priority"])
                    if prefilled["priority"] in PRIORITY_OPTIONS else 1,
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
