"""
Computer Vision output → COBie row conversion.

Implements the defect semantic extraction layer bridging from
image-domain CV outputs (masks, bounding boxes, class labels) to
COBie-compatible tabular records.

This is the implementation of Stages 3-5 of the pipeline:
    Stage 3 — Geolocate (pixel to 3D to chainage)
    Stage 4 — Extract attributes (width, moisture code, severity)
    Stage 5 — Populate COBie rows

Stages 1-2 (raw acquisition and CNN inference) are assumed upstream.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Any


# -----------------------------------------------------------------------------
# CV class label → ontology defect type mapping
# -----------------------------------------------------------------------------
CV_CLASS_TO_DEFECT_TYPE = {
    "crack":            "Cracks",
    "longitudinal_crack": "Cracks",
    "transverse_crack": "Cracks",
    "diagonal_crack":   "Cracks",
    "spall":            "Spalls",
    "spalling":         "Spalls",
    "leakage":          "LeakingJoints",
    "leakage_joint":    "LeakingJoints",
    "efflorescence":    "Staining",
    "staining":         "Staining",
    "delamination":     "Delaminations",
}


# -----------------------------------------------------------------------------
# Severity assignment
# -----------------------------------------------------------------------------
def assign_spall_severity(depth_mm: float, rebar_cover_mm: float = 45) -> str:
    """Assign AASHTO spall grade S-1 through S-4 by depth relative to rebar."""
    if depth_mm < 51:  # less than 2 inches
        return "S-1"
    elif depth_mm < rebar_cover_mm:
        return "S-1"
    elif depth_mm < rebar_cover_mm + 15:
        return "S-2"
    elif depth_mm < rebar_cover_mm + 30:
        return "S-3"
    else:
        return "S-4"


def classify_moisture_code_from_color(
    red_mean: float, saturation: float, brightness_delta: float,
) -> str:
    """
    Classify moisture state from RGB region color analysis.

    Thresholds are illustrative — in production, train a classifier
    on labelled inspector-verified samples.
    """
    if brightness_delta < 5 and saturation < 10:
        return "D"
    if saturation < 20 and brightness_delta < 15:
        return "PM"
    if red_mean < 120 and saturation > 20:
        return "M"
    if brightness_delta > 40:
        return "GS"
    if brightness_delta > 60:
        return "F"
    return "D"


def assign_priority(defect_type: str, severity: str, moisture: str) -> str:
    """Assign HIGH / MEDIUM / LOW priority using the decision logic."""
    if moisture in ["GS", "F"]:
        return "HIGH"
    if severity in ["S-3", "S-4"]:
        return "HIGH"
    if severity == "S-2" or moisture == "M":
        return "MEDIUM"
    return "LOW"


# -----------------------------------------------------------------------------
# Pixel to chainage projection (stub — real implementation needs BIM geometry)
# -----------------------------------------------------------------------------
def pixel_to_chainage(
    pixel_x: int, pixel_y: int,
    camera_pose: Dict[str, Any],
    image_metadata: Dict[str, Any],
) -> Dict[str, float]:
    """
    Back-project a pixel to tunnel chainage via camera pose and BIM.

    This is a stub — real implementation requires:
        1. Camera intrinsics (focal length, principal point)
        2. Camera pose in BIM CRS (6-DOF)
        3. BIM geometry for ray intersection

    Returns dict with chainage_m, ring_id, circumferential_angle.
    """
    # Simplified linear interpolation for demo
    chainage_offset_m = pixel_x / image_metadata.get("width", 4096) * 12.0
    base_chainage = camera_pose.get("position", [850, 0, 0])[0]

    chainage = base_chainage + chainage_offset_m
    ring_id = int(chainage * 1.5)  # ~1.5 rings per meter, typical

    # Circumferential angle from pixel_y
    image_height = image_metadata.get("height", 2160)
    angle_deg = (pixel_y / image_height - 0.5) * 180

    return {
        "chainage_m": round(chainage, 2),
        "ring_id": ring_id,
        "circumferential_angle_deg": round(angle_deg, 1),
        "position_zone": _angle_to_zone(angle_deg),
    }


def _angle_to_zone(angle_deg: float) -> str:
    if -30 <= angle_deg <= 30:
        return "Crown"
    elif 30 < angle_deg <= 90:
        return "RightSideWall_Upper"
    elif 90 < angle_deg <= 150:
        return "RightSideWall_Lower"
    elif -90 <= angle_deg < -30:
        return "LeftSideWall_Upper"
    elif -150 <= angle_deg < -90:
        return "LeftSideWall_Lower"
    else:
        return "Invert"


# -----------------------------------------------------------------------------
# Main conversion function
# -----------------------------------------------------------------------------
def convert_cv_output_to_cobie_rows(
    cv_result: Dict[str, Any],
    tunnel_id: str = "TUN-A",
) -> List[Dict[str, Any]]:
    """
    Convert CV pipeline output to COBie spreadsheet rows.

    Expected cv_result structure:
        {
            "image_path": str,
            "timestamp": str (ISO-8601),
            "camera_pose": {position: [x,y,z], orientation: [...]},
            "image_metadata": {width: int, height: int},
            "depth_map_path": str | None,
            "masks": [
                {
                    "id": str,
                    "class_label": str,
                    "confidence": float,
                    "pixel_bbox": [x, y, w, h],
                    "pixel_centroid": [x, y],
                    "measurements": {width_mm, depth_mm, area_cm2, ...},
                    "color_stats": {red_mean, saturation, brightness_delta},
                },
                ...
            ]
        }

    Returns a list of COBie row dicts ready to write to spreadsheet.
    """
    rows = []
    timestamp = cv_result.get("timestamp", datetime.utcnow().isoformat())
    image_path = cv_result.get("image_path", "")

    for mask in cv_result.get("masks", []):
        # Geolocate
        geo = pixel_to_chainage(
            mask["pixel_centroid"][0],
            mask["pixel_centroid"][1],
            cv_result.get("camera_pose", {}),
            cv_result.get("image_metadata", {}),
        )

        # Classify
        defect_type = CV_CLASS_TO_DEFECT_TYPE.get(
            mask["class_label"].lower(), "Unclassified"
        )

        # Attributes
        measurements = mask.get("measurements", {})
        color_stats = mask.get("color_stats", {})

        moisture = classify_moisture_code_from_color(
            color_stats.get("red_mean", 128),
            color_stats.get("saturation", 30),
            color_stats.get("brightness_delta", 20),
        )

        severity = ""
        if defect_type == "Spalls" and "depth_mm" in measurements:
            severity = assign_spall_severity(measurements["depth_mm"])

        priority = assign_priority(defect_type, severity, moisture)

        defect_name = f"DEFECT-{tunnel_id}-{uuid.uuid4().hex[:8]}"
        component_name = f"Ring_{geo['ring_id']}"

        # Main COBie.Defect row
        rows.append({
            "sheet": "COBie.Defect",
            "Name": defect_name,
            "CreatedBy": "cv_pipeline_v2.3",
            "CreatedOn": timestamp,
            "Degree": severity or priority,
            "SourceName": "AutomatedVisualInspection",
            "DefectTypeName": defect_type,
            "ComponentName": component_name,
            "ExtSystem": "RGB_CV_Pipeline",
            "ExtObject": image_path,
            "ExtIdentifier": mask["id"],
            "Description": (
                f"CNN confidence {mask['confidence']:.2f}; "
                f"chainage K{int(geo['chainage_m'])}+"
                f"{int((geo['chainage_m'] % 1) * 1000):03d}; "
                f"{geo['position_zone']}; "
                f"moisture {moisture}"
            ),
        })

        # COBie.RealTimeData row for moisture
        rows.append({
            "sheet": "COBie.RealTimeData",
            "Name": f"MEAS-{uuid.uuid4().hex[:8]}",
            "ComponetName": component_name,
            "RealTimeDataValue": moisture,
            "CreatedOn": timestamp,
            "ExtSystem": "RGB_MoistureClassifier",
        })

        # COBie.RealTimeData rows for dimensional measurements
        for key, label in [
            ("width_mm", "CrackWidth"),
            ("depth_mm", "SpallDepth"),
            ("area_cm2", "DefectExtent"),
        ]:
            if key in measurements and measurements[key] is not None:
                unit = "mm" if "mm" in key else "cm2"
                rows.append({
                    "sheet": "COBie.RealTimeData",
                    "Name": f"MEAS-{uuid.uuid4().hex[:8]}",
                    "ComponetName": component_name,
                    "RealTimeDataValue": f"{measurements[key]:.2f} {unit}",
                    "CreatedOn": timestamp,
                    "ExtSystem": "RGBD_Measurement",
                    "ExtIdentifier": f"{defect_name}_{label}",
                })

    return rows


def defects_to_cobie_rows(
    defects: List[Dict[str, Any]],
    tunnel_id: str = "TUN-A",
) -> List[Dict[str, Any]]:
    """
    Map registered defect records to COBie rows, using the same schema the
    CV bridge emits (COBie.Defect + COBie.RealTimeData) — so a report or
    handover can carry COBie-formatted data straight from the register,
    without going through the CV pipeline.
    """
    rows: List[Dict[str, Any]] = []
    for d in defects:
        comp = f"Ring_{d.get('ring_id', '?')}"
        name = d.get("defect_id") or f"DEFECT-{tunnel_id}-{uuid.uuid4().hex[:8]}"
        created = (d.get("discovery_date") or d.get("created_on")
                   or datetime.utcnow().date().isoformat())
        rows.append({
            "sheet": "COBie.Defect",
            "Name": name,
            "CreatedBy": d.get("inspector", "tunnel_dt"),
            "CreatedOn": created,
            "Degree": d.get("severity") or d.get("priority", ""),
            "SourceName": d.get("source", "Inspection"),
            "DefectTypeName": d.get("defect_type", "Unclassified"),
            "ComponentName": comp,
            "ExtSystem": "TunnelDT",
            "ExtObject": d.get("tunnel_id", tunnel_id),
            "ExtIdentifier": name,
            "Description": (
                f"K{float(d.get('chainage_m') or 0):.0f}m; "
                f"{d.get('position', '-')}; priority {d.get('priority', '-')}"
            ),
        })
        for key, label, unit in [
            ("crack_width_mm", "CrackWidth", "mm"),
            ("spall_depth_mm", "SpallDepth", "mm"),
            ("area_cm2", "DefectExtent", "cm2"),
        ]:
            val = d.get(key)
            if not val:
                continue
            try:
                vtxt = f"{float(val):.2f} {unit}"
            except (TypeError, ValueError):
                continue
            rows.append({
                "sheet": "COBie.RealTimeData",
                "Name": f"MEAS-{uuid.uuid4().hex[:8]}",
                "ComponentName": comp,
                "RealTimeDataValue": vtxt,
                "CreatedOn": created,
                "ExtSystem": "TunnelDT_Measurement",
                "ExtIdentifier": f"{name}_{label}",
            })
    return rows


def rows_to_dataframe(rows: List[Dict[str, Any]]):
    """Convert the mixed-sheet row list to a pandas DataFrame, grouped by sheet."""
    import pandas as pd
    return pd.DataFrame(rows)
