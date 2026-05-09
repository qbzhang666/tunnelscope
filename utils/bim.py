"""
BIM utilities — as-built record lookup
======================================

Loads `data/bim_as_built.json` and resolves a defect's ring/chainage
to the construction segment that ring belongs to. Returns the
as-built record (concrete mix, reinforcement, joint type, contractor,
construction notes, repair history) for that segment.

Used by:
    - pages/2_Defect_Detail.py — inline BIM badge near the FMEA chain
      Component step, with full as-built details available in an
      expandable section.

DESIGN NOTES
------------
1. Granularity is segment-level, not ring-level. Each tunnel is split
   into ~5 construction segments, each ~50–600 rings wide, with
   common attributes (concrete mix, reinforcement spec, contractor,
   construction dates). This matches how real BIM systems actually
   group records — by construction batch, not by individual ring.
2. The repair_history list is per-tunnel (not per-segment), keyed by
   ring_id. Stage 2 only reads it; Stage 3 (Rev 9 or later) will add
   write-back from completed work orders.
3. All data is synthetic but plausible. The construction_year_range,
   design_standards, and concrete-mix parameters reflect the real
   construction eras and Australian standards in force at the time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
BIM_FILE = DATA_DIR / "bim_as_built.json"


# -----------------------------------------------------------------------------
# Loading
# -----------------------------------------------------------------------------
def load_bim_as_built() -> Dict[str, Any]:
    """Load the BIM as-built JSON. Returns empty stub if file missing."""
    if not BIM_FILE.exists():
        return {"_meta": {}, "tunnels": {}}
    try:
        with open(BIM_FILE) as f:
            return json.load(f)
    except Exception:
        return {"_meta": {}, "tunnels": {}}


def is_demonstration_data() -> bool:
    """Whether the loaded BIM data carries the demonstration-data flag."""
    bim = load_bim_as_built()
    return bool(bim.get("_meta", {}).get("demonstration_data"))


def get_tunnel_record(tunnel_id: str) -> Optional[Dict[str, Any]]:
    """Return the full tunnel-level record (segments + tunnel attributes)."""
    bim = load_bim_as_built()
    return bim.get("tunnels", {}).get(tunnel_id)


# -----------------------------------------------------------------------------
# Ring → segment lookup
# -----------------------------------------------------------------------------
def find_segment_for_ring(
    tunnel_id: str,
    ring_id: Optional[Any] = None,
    chainage_m: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Resolve a ring ID (or chainage) to the construction segment it
    belongs to. Returns the segment dict, or None if no segment
    contains the given location.

    Pass either ring_id or chainage_m. ring_id takes precedence; if
    only chainage_m is given, we use that.

    Why this exists: defects in the JSON have ring_id values like
    1247, 1158, etc. — each ring belongs to one of ~5 segments per
    tunnel, and the segment carries the actual as-built attributes
    (mix, reinforcement, contractor). This function is the join.
    """
    tunnel = get_tunnel_record(tunnel_id)
    if not tunnel:
        return None

    segments = tunnel.get("construction_segments", [])
    if not segments:
        return None

    # Prefer ring_id when available
    ring_int: Optional[int] = None
    if ring_id is not None and ring_id != "" and str(ring_id) != "Unknown":
        try:
            ring_int = int(ring_id)
        except (ValueError, TypeError):
            ring_int = None

    if ring_int is not None:
        for seg in segments:
            r_lo, r_hi = seg.get("ring_range", [0, 0])
            if r_lo <= ring_int <= r_hi:
                return seg
        # Out of range — return None so the UI can flag it
        return None

    # Fall back to chainage if ring is unusable
    if chainage_m is not None and chainage_m > 0:
        for seg in segments:
            c_lo, c_hi = seg.get("chainage_range_m", [0, 0])
            if c_lo <= chainage_m <= c_hi:
                return seg

    return None


# -----------------------------------------------------------------------------
# Repair history lookup
# -----------------------------------------------------------------------------
def get_repair_history_for_ring(
    tunnel_id: str,
    ring_id: Optional[Any],
    radius: int = 5,
) -> List[Dict[str, Any]]:
    """
    Return repair-history entries for the given ring or its neighbours.

    `radius` controls how many rings either side of the target also
    count as "nearby" — useful because a leak at Ring 1158 might be
    informed by knowing a related repair was logged at Ring 1156.
    """
    tunnel = get_tunnel_record(tunnel_id)
    if not tunnel:
        return []

    history = tunnel.get("repair_history", [])
    if not history:
        return []

    try:
        ring_int = int(ring_id) if ring_id is not None else None
    except (ValueError, TypeError):
        ring_int = None

    if ring_int is None:
        return []

    out = []
    for entry in history:
        entry_ring = entry.get("ring_id")
        if entry_ring is None:
            continue
        try:
            entry_ring_int = int(entry_ring)
        except (ValueError, TypeError):
            continue
        if abs(entry_ring_int - ring_int) <= radius:
            out.append(entry)
    return out


# -----------------------------------------------------------------------------
# Convenience: assemble the full BIM context for a defect
# -----------------------------------------------------------------------------
def get_bim_context(defect: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pull together everything Defect Detail needs to render the BIM
    badge + expandable section in one call. Returns a dict with keys:

        tunnel       — the tunnel-level record (None if unknown)
        segment      — the construction segment containing this ring
                       (None if ring out of range or tunnel unknown)
        repairs      — nearby repair-history entries (possibly empty)
        is_demo_data — whether the data carries the demo flag
        ring_in_range — bool: True if the defect's ring falls within
                       any segment, False if it's out of bounds
    """
    tunnel_id = defect.get("tunnel_id")
    ring_id = defect.get("ring_id")
    chainage_m = defect.get("chainage_m")

    tunnel = get_tunnel_record(tunnel_id) if tunnel_id else None
    segment = (
        find_segment_for_ring(tunnel_id, ring_id, chainage_m)
        if tunnel_id else None
    )
    repairs = (
        get_repair_history_for_ring(tunnel_id, ring_id)
        if tunnel_id else []
    )

    return {
        "tunnel": tunnel,
        "segment": segment,
        "repairs": repairs,
        "is_demo_data": is_demonstration_data(),
        "ring_in_range": segment is not None and tunnel is not None,
    }
