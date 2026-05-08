"""
CV to COBie Bridge — page 4
===========================

Interactive demonstration of the multimodal defect semantic extraction
layer. Takes structured CV pipeline output (JSON) — typically produced
by an upstream computer-vision pipeline running over RGB / RGBD /
Thermal / GPR data — and converts it into COBie spreadsheet rows
through the three sub-stages:

    Stage A — geolocate (pixel to 3D to chainage)
    Stage B — extract attributes (dimensions, moisture code, severity)
    Stage C — component linkage and COBie row population
"""

import json
import streamlit as st
import pandas as pd

from utils.cv_to_cobie import (
    convert_cv_output_to_cobie_rows,
    CV_CLASS_TO_DEFECT_TYPE,
    assign_spall_severity, classify_moisture_code_from_color, assign_priority,
    pixel_to_chainage,
)
from utils.styling import apply_custom_css

st.set_page_config(page_title="CV → COBie Bridge", layout="wide")
apply_custom_css()

st.title("CV → COBie bridge")
st.caption(
    "Demonstrates how structured computer-vision output (masks, bounding "
    "boxes, class labels) from a multimodal survey is converted to COBie "
    "spreadsheet rows through the defect semantic extraction layer."
)

st.info(
    "**Got a single inspection photo or a written report?** Use the "
    "**Ingest** page in the sidebar — it's designed for the common case "
    "of a single source. This page is for structured output from an "
    "upstream multimodal CV pipeline."
)

# -----------------------------------------------------------------------------
# Sample CV output
# -----------------------------------------------------------------------------
SAMPLE_CV_OUTPUT = {
    "image_path": "/surveys/TunnelA/2024-03-15/IMG_00847.jpg",
    "timestamp": "2024-03-15T11:23:45Z",
    "camera_pose": {
        "position": [851.3, -12.4, 2.1],
        "orientation": [0.12, 0.05, -0.87, 0.47],
    },
    "image_metadata": {"width": 4096, "height": 2160},
    "depth_map_path": "/surveys/TunnelA/2024-03-15/DEPTH_00847.tiff",
    "masks": [
        {
            "id": "mask_001",
            "class_label": "leakage_joint",
            "confidence": 0.92,
            "pixel_bbox": [1240, 890, 340, 230],
            "pixel_centroid": [1410, 1005],
            "measurements": {"area_cm2": 63.4, "trail_length_m": 0.58},
            "color_stats": {"red_mean": 100, "saturation": 45, "brightness_delta": 48},
        },
        {
            "id": "mask_002",
            "class_label": "spall",
            "confidence": 0.88,
            "pixel_bbox": [2200, 1100, 180, 120],
            "pixel_centroid": [2290, 1160],
            "measurements": {"depth_mm": 58, "area_cm2": 112},
            "color_stats": {"red_mean": 140, "saturation": 18, "brightness_delta": 8},
        },
    ],
}

# -----------------------------------------------------------------------------
# Input section
# -----------------------------------------------------------------------------
st.subheader("Input — CV pipeline output")

input_mode = st.radio(
    "Input source",
    options=["Use sample data", "Upload JSON", "Paste JSON"],
    horizontal=True,
)

cv_output = None

if input_mode == "Use sample data":
    cv_output = SAMPLE_CV_OUTPUT
    with st.expander("View sample data"):
        st.code(json.dumps(cv_output, indent=2), language="json")

elif input_mode == "Upload JSON":
    uploaded = st.file_uploader("Upload CV pipeline output (JSON)", type=["json"])
    if uploaded:
        cv_output = json.load(uploaded)
        st.success(f"Loaded {len(cv_output.get('masks', []))} masks.")

elif input_mode == "Paste JSON":
    pasted = st.text_area(
        "Paste JSON here",
        value=json.dumps(SAMPLE_CV_OUTPUT, indent=2),
        height=300,
    )
    try:
        cv_output = json.loads(pasted)
    except json.JSONDecodeError as e:
        st.error(f"Invalid JSON: {e}")

st.divider()

# -----------------------------------------------------------------------------
# Per-mask processing walkthrough
# -----------------------------------------------------------------------------
if cv_output:
    st.subheader("Stage-by-stage processing")

    for i, mask in enumerate(cv_output.get("masks", [])):
        with st.expander(
            f"Mask {i+1}: {mask.get('class_label')} "
            f"(confidence {mask.get('confidence', 0):.2f})",
            expanded=(i == 0),
        ):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**Stage A — Geolocate**")
                geo = pixel_to_chainage(
                    mask["pixel_centroid"][0],
                    mask["pixel_centroid"][1],
                    cv_output.get("camera_pose", {}),
                    cv_output.get("image_metadata", {}),
                )
                st.caption("Pixel centroid → 3D → chainage")
                st.code(f"""chainage_m: {geo['chainage_m']}
ring_id: {geo['ring_id']}
angle: {geo['circumferential_angle_deg']}°
zone: {geo['position_zone']}""", language=None)

            with col2:
                st.markdown("**Stage B — Extract attributes**")
                defect_type = CV_CLASS_TO_DEFECT_TYPE.get(
                    mask["class_label"].lower(), "Unclassified"
                )
                color_stats = mask.get("color_stats", {})
                moisture = classify_moisture_code_from_color(
                    color_stats.get("red_mean", 128),
                    color_stats.get("saturation", 30),
                    color_stats.get("brightness_delta", 20),
                )
                measurements = mask.get("measurements", {})
                severity = ""
                if defect_type == "Spalls" and "depth_mm" in measurements:
                    severity = assign_spall_severity(measurements["depth_mm"])
                priority = assign_priority(defect_type, severity, moisture)

                st.caption("Classify and measure")
                st.code(f"""defect_type: {defect_type}
moisture_code: {moisture}
severity: {severity or 'N/A'}
priority: {priority}""", language=None)

            with col3:
                st.markdown("**Stage C — Link component**")
                component = f"Ring_{geo['ring_id']}"
                st.caption("Find nearest BIM component")
                st.code(f"""component: {component}
cobie_sheet: Defect
cobie_row: {mask['id']}""", language=None)

    st.divider()

    # ------------------------------------------------------------------
    # Final COBie output
    # ------------------------------------------------------------------
    st.subheader("Output — COBie spreadsheet rows")

    rows = convert_cv_output_to_cobie_rows(cv_output, tunnel_id="TUN-A")
    df = pd.DataFrame(rows)

    sheets = df["sheet"].unique() if not df.empty else []
    for sheet in sheets:
        sheet_df = df[df["sheet"] == sheet].drop(columns=["sheet"])
        sheet_df = sheet_df.dropna(axis=1, how="all")
        st.markdown(f"**{sheet}** — {len(sheet_df)} row(s)")
        st.dataframe(sheet_df, use_container_width=True, hide_index=True)

    col1, col2 = st.columns(2)
    with col1:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download all rows (CSV)",
            csv, "cobie_rows.csv", "text/csv",
        )
    with col2:
        jsonstr = df.to_json(orient="records", indent=2).encode("utf-8")
        st.download_button(
            "Download as JSON",
            jsonstr, "cobie_rows.json", "application/json",
        )

    st.info(
        "These rows are ready to be written to the extended COBie "
        "spreadsheet, after which the COBie-to-OWL converter (Yu et al. "
        "2021) populates the ABox of the maintenance ontology."
    )
