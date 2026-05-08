"""
Ingest utilities — text and image inputs to defect dicts
========================================================

Converts uploaded inspection reports (PDF/DOCX/TXT) and inspection
images (PNG/JPG/JPEG) into the same defect dictionary shape that
`ontology_loader.load_defects()` produces. Once a file passes through
this module, the rest of the app treats it identically to a defect
loaded from the ontology.

Two routes are supported:
    Route A — Manual entry: the user uploads a file for the record,
              then types the defect type and measurements.
    Route B — Heuristic stub: filename + simple rules pre-fill the
              defect type. Clearly labelled as a demo placeholder
              for an upstream ML pipeline.

Both routes converge on the same defect dict, so downstream pages
(Defect Register, Defect Detail) need no changes.
"""

from __future__ import annotations

import io
import os
import re
from datetime import date
from typing import Dict, List, Optional, Tuple


# -----------------------------------------------------------------------------
# CV-class to ontology defect-type mapping
# -----------------------------------------------------------------------------
DEFECT_TYPE_OPTIONS = [
    "Cracks",
    "Spalls",
    "LeakingJoints",
    "Efflorescence",
    "RebarCorrosion",
    "Delamination",
    "Honeycombing",
    "ConstructionJointDefect",
    "Unclassified",
]

PRIORITY_OPTIONS = ["HIGH", "MEDIUM", "LOW"]

POSITION_OPTIONS = ["Crown", "Springline_L", "Springline_R",
                    "Invert", "Sidewall_L", "Sidewall_R"]


# Filename keyword -> defect-type heuristic. Crude but useful for the
# Route B stub. Order matters — first match wins.
FILENAME_KEYWORDS: List[Tuple[str, str]] = [
    ("crack",      "Cracks"),
    ("spall",      "Spalls"),
    ("leak",       "LeakingJoints"),
    ("efflor",     "Efflorescence"),
    ("rust",       "RebarCorrosion"),
    ("rebar",      "RebarCorrosion"),
    ("delam",      "Delamination"),
    ("honeycomb",  "Honeycombing"),
    ("joint",      "ConstructionJointDefect"),
]


# Defect-type → single-letter code used in defect IDs to match the
# existing ontology convention (e.g. D-1247-L for a leak at Ring 1247).
DEFECT_TYPE_LETTER: Dict[str, str] = {
    "Cracks": "C",
    "Spalls": "S",
    "LeakingJoints": "L",
    "Efflorescence": "E",
    "RebarCorrosion": "R",
    "Delamination": "D",
    "Honeycombing": "H",
    "ConstructionJointDefect": "J",
    "Unclassified": "U",
}


def heuristic_defect_type_from_filename(filename: str) -> str:
    """Pick a defect type from filename keywords. Returns 'Unclassified'
    if no keyword matches."""
    lower = filename.lower()
    for keyword, defect_type in FILENAME_KEYWORDS:
        if keyword in lower:
            return defect_type
    return "Unclassified"


def build_ingested_defect_id(
    ring_id: str,
    defect_type: str,
    sequence_number: int,
) -> str:
    """
    Build a defect ID matching the ontology convention.

    Pattern: D-{ring}-{type_letter}-i{seq}

    The 'i' prefix on the sequence number signals that this defect was
    ingested via the upload page rather than loaded from the ontology.
    Examples:
        D-1247-C-i01    Crack at Ring 1247, first ingested
        D-0923-S-i02    Spall at Ring 0923, second ingested
        D-Unknown-L-i03 Leak at unknown ring, third ingested

    Falls back to 'Unknown' if ring_id is empty.
    """
    ring_clean = (ring_id or "Unknown").strip().replace(" ", "")
    type_letter = DEFECT_TYPE_LETTER.get(defect_type, "U")
    return f"D-{ring_clean}-{type_letter}-i{sequence_number:02d}"


# -----------------------------------------------------------------------------
# Text extraction (Route A and B for documents)
# -----------------------------------------------------------------------------
def extract_text_from_upload(file_bytes: bytes, filename: str) -> str:
    """
    Pull plain text out of a PDF / DOCX / TXT upload.

    Uses graceful fallbacks: if the relevant library isn't installed,
    returns an empty string and the caller falls back to manual entry.
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".txt":
        try:
            return file_bytes.decode("utf-8", errors="replace")
        except Exception:
            return ""

    if ext == ".pdf":
        try:
            import pypdf  # lightweight PDF reader
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            pages = [p.extract_text() or "" for p in reader.pages]
            return "\n".join(pages)
        except ImportError:
            try:
                from PyPDF2 import PdfReader  # fallback
                reader = PdfReader(io.BytesIO(file_bytes))
                pages = [p.extract_text() or "" for p in reader.pages]
                return "\n".join(pages)
            except Exception:
                return ""
        except Exception:
            return ""

    if ext in (".docx", ".doc"):
        try:
            import docx  # python-docx
            d = docx.Document(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in d.paragraphs)
        except Exception:
            return ""

    return ""


# -----------------------------------------------------------------------------
# Heuristic field extraction from inspection report text (Route B)
# -----------------------------------------------------------------------------
_RING_PATTERN = re.compile(r"\b(?:ring|rg)[\s#\-:]*?(\d{2,5})\b", re.IGNORECASE)
_CHAIN_PATTERN = re.compile(r"\b(?:chainage|ch|km|k)[\s\-:]*?(\d+(?:\.\d+)?)\b",
                            re.IGNORECASE)
_WIDTH_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE)
_DEPTH_PATTERN = re.compile(r"depth[^\d]{0,10}(\d+(?:\.\d+)?)\s*mm",
                            re.IGNORECASE)


def heuristic_fields_from_text(text: str) -> Dict[str, Optional[str]]:
    """
    Pull obvious fields out of inspection-report text using regex.
    Returns a dict where any field that couldn't be found is None.

    This is a stub — a real deployment would use an LLM-assisted
    extractor against a defined schema, the same way we extracted FMEA
    chains from AASHTO. The page UI clearly labels this as a demo.
    """
    out: Dict[str, Optional[str]] = {
        "ring_id": None,
        "chainage_m": None,
        "crack_width_mm": None,
        "spall_depth_mm": None,
        "defect_type_guess": None,
    }

    if not text:
        return out

    m = _RING_PATTERN.search(text)
    if m:
        out["ring_id"] = m.group(1)

    m = _CHAIN_PATTERN.search(text)
    if m:
        out["chainage_m"] = float(m.group(1))

    m = _WIDTH_PATTERN.search(text)
    if m:
        out["crack_width_mm"] = float(m.group(1))

    m = _DEPTH_PATTERN.search(text)
    if m:
        out["spall_depth_mm"] = float(m.group(1))

    lower = text.lower()
    for keyword, defect_type in FILENAME_KEYWORDS:
        if keyword in lower:
            out["defect_type_guess"] = defect_type
            break

    return out


# -----------------------------------------------------------------------------
# Build a defect dict (the canonical app shape)
# -----------------------------------------------------------------------------
def build_defect_dict(
    *,
    defect_id: str,
    defect_type: str,
    description: str,
    ring_id: str,
    chainage_m: float,
    position: str,
    priority: str,
    evidence_modalities: List[str],
    source_filename: str,
    source_kind: str,  # "image" | "text"
    measurements: Optional[Dict] = None,
) -> Dict:
    """
    Construct the same dict shape that `ontology_loader.load_defects()`
    produces, so downstream pages render the record without changes.

    The returned dict can be appended to `st.session_state.defects`
    directly.
    """
    from utils.fmea_chain import compute_completeness

    measurements = measurements or {}
    score, _, _ = compute_completeness(defect_type, evidence_modalities)

    # Build the modality_evidence dict that Defect Detail expects.
    evidence: Dict[str, Dict] = {}
    for mod in evidence_modalities:
        if mod == "InspectionReport":
            evidence["RGB"] = {
                "status": "Reported by inspector",
                "finding": (
                    f"{defect_type} reported in {source_filename}"
                ),
                "fmea_level": "defect_qualitative",
            }
            continue
        evidence[mod] = {
            "status": "Captured",
            "finding": _summarise_measurements(defect_type, measurements),
            "fmea_level": _primary_level_for(mod),
        }

    return {
        "defect_id": defect_id,
        "description": description,
        "defect_type": defect_type,
        "ring_id": ring_id,
        "chainage_m": float(chainage_m) if chainage_m else 0.0,
        "position": position,
        "priority": priority,
        "discovered_on": date.today().isoformat(),
        "status": "Active",
        "completeness_score": score,
        "estimated_cost_aud": 0,
        "modality_evidence": evidence,
        "source_filename": source_filename,
        "source_kind": source_kind,
        "ingested": True,  # Marker that this came from the Ingest page
        "measurements": measurements,
        "fmea_chain": [],  # Will fall back to default chain in Detail page
    }


def _primary_level_for(modality: str) -> str:
    levels = {
        "RGB":     "defect_qualitative",
        "RGBD":    "indicator_quantitative",
        "Thermal": "cause_qualitative",
        "GPR":     "cause_subsurface",
    }
    return levels.get(modality, "defect_qualitative")


def _summarise_measurements(defect_type: str, m: Dict) -> str:
    parts = []
    if "crack_width_mm" in m and m["crack_width_mm"]:
        parts.append(f"width {m['crack_width_mm']} mm")
    if "spall_depth_mm" in m and m["spall_depth_mm"]:
        parts.append(f"depth {m['spall_depth_mm']} mm")
    if "area_cm2" in m and m["area_cm2"]:
        parts.append(f"area {m['area_cm2']} cm²")
    return "; ".join(parts) if parts else f"{defect_type} captured"
