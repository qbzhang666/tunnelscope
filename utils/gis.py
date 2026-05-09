"""
GIS utilities — tunnel maps and click-to-chainage projection
============================================================

Loads tunnel alignment geometry, builds Folium maps with layered
overlays, and projects map-click coordinates back into the tunnel
reference system (chainage, ring, position).

Used by:
    - pages/0_Ingest.py — operator clicks where they took the photo,
      the system back-derives ring_id and chainage_m
    - pages/1_Defect_Register.py — overview map of all defects
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import folium

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
GEOMETRY_FILE = DATA_DIR / "tunnel_geometry.json"


# -----------------------------------------------------------------------------
# Geometry loading
# -----------------------------------------------------------------------------
def load_tunnel_geometry() -> Dict[str, Any]:
    """Load tunnel alignment data from JSON. Returns dict with 'tunnels' key."""
    if not GEOMETRY_FILE.exists():
        return {"tunnels": []}
    with open(GEOMETRY_FILE) as f:
        return json.load(f)


def get_tunnel(tunnel_id: str) -> Optional[Dict[str, Any]]:
    """Look up a tunnel record by ID."""
    geom = load_tunnel_geometry()
    for t in geom.get("tunnels", []):
        if t["tunnel_id"] == tunnel_id:
            return t
    return None


def list_tunnels() -> List[Dict[str, Any]]:
    """Return all tunnel records."""
    return load_tunnel_geometry().get("tunnels", [])


# -----------------------------------------------------------------------------
# Geodesic helpers — sufficient accuracy for tunnel-scale projection
# -----------------------------------------------------------------------------
EARTH_RADIUS_M = 6_371_000.0


def haversine_m(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Great-circle distance in metres between two (lat, lon) points."""
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (math.sin(dlat / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _project_point_onto_segment(
    pt: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
) -> Tuple[float, Tuple[float, float], float]:
    """
    Project pt onto the line segment a→b.

    Returns (along_distance_m, projected_point, perpendicular_distance_m).
    `along_distance_m` is clipped to [0, segment_length].

    Uses a local equirectangular approximation, which is fine at the
    metre scale we care about for tunnels.
    """
    # Local origin at segment start
    lat0 = a[0]
    lat_to_m = 111_000.0
    lon_to_m = 111_000.0 * math.cos(math.radians(lat0))

    ax, ay = 0.0, 0.0
    bx = (b[1] - a[1]) * lon_to_m
    by = (b[0] - a[0]) * lat_to_m
    px = (pt[1] - a[1]) * lon_to_m
    py = (pt[0] - a[0]) * lat_to_m

    seg_dx, seg_dy = bx - ax, by - ay
    seg_len_sq = seg_dx * seg_dx + seg_dy * seg_dy
    if seg_len_sq < 1e-9:
        return 0.0, a, math.hypot(px, py)

    t = max(0.0, min(1.0, (px * seg_dx + py * seg_dy) / seg_len_sq))
    proj_x = t * seg_dx
    proj_y = t * seg_dy
    along = math.hypot(proj_x, proj_y)
    perp = math.hypot(px - proj_x, py - proj_y)

    proj_lat = a[0] + (proj_y / lat_to_m)
    proj_lon = a[1] + (proj_x / lon_to_m)
    return along, (proj_lat, proj_lon), perp


# -----------------------------------------------------------------------------
# Click → chainage / ring / tunnel resolver
# -----------------------------------------------------------------------------
def click_to_tunnel_location(
    click_lat: float,
    click_lon: float,
    candidate_tunnel_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Resolve a map click coordinate to (tunnel, chainage, ring).

    Walks each tunnel's polyline, finds the closest point on any segment,
    and returns the tunnel + along-distance + ring index for that point.

    If `candidate_tunnel_ids` is given, only those tunnels are considered.
    Otherwise all tunnels are tried; the closest wins.

    Returns None if no tunnel is within 500 m of the click (operator
    probably misclicked).
    """
    best: Optional[Dict[str, Any]] = None
    best_perp = float("inf")

    for tunnel in list_tunnels():
        if candidate_tunnel_ids and tunnel["tunnel_id"] not in candidate_tunnel_ids:
            continue
        alignment = tunnel.get("alignment", [])
        if len(alignment) < 2:
            continue

        cumulative_m = 0.0
        for i in range(len(alignment) - 1):
            a = tuple(alignment[i])
            b = tuple(alignment[i + 1])
            along, proj, perp = _project_point_onto_segment(
                (click_lat, click_lon), a, b
            )
            if perp < best_perp:
                best_perp = perp
                ring_length = tunnel.get("ring_length_m", 1.6)
                chainage = cumulative_m + along
                ring = int(round(chainage / ring_length))
                best = {
                    "tunnel_id": tunnel["tunnel_id"],
                    "tunnel_label": tunnel["label"],
                    "chainage_m": round(chainage, 1),
                    "ring_id": ring,
                    "perpendicular_offset_m": round(perp, 1),
                    "projected_lat": proj[0],
                    "projected_lon": proj[1],
                }
            cumulative_m += haversine_m(a, b)

    if best is None or best_perp > 500.0:
        return None
    return best


# -----------------------------------------------------------------------------
# Map builders
# -----------------------------------------------------------------------------
TUNNEL_COLOURS = {"TUN-A": "#1f78b4", "TUN-B": "#33a02c"}
PRIORITY_COLOURS = {"HIGH": "#d62728", "MEDIUM": "#ff7f0e", "LOW": "#999999"}


def _midpoint(coords_list: List[List[float]]) -> Tuple[float, float]:
    """Return the centroid of a list of (lat, lon) pairs."""
    if not coords_list:
        return (-37.8200, 144.9500)  # Melbourne CBD fallback
    lats = [c[0] for c in coords_list]
    lons = [c[1] for c in coords_list]
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def build_overview_map(
    defects: List[Dict[str, Any]],
    selected_tunnel_id: Optional[str] = None,
    height: int = 500,
) -> folium.Map:
    """
    Build the read-only overview map for the Defect Register.

    Renders both tunnel alignments + every defect as a coloured marker
    (colour by priority). Click on a marker → popup with defect ID +
    description; the popup HTML embeds the defect ID so the page can
    pick it up via the st_folium return dict.
    """
    geom = load_tunnel_geometry()
    tunnels = geom.get("tunnels", [])

    # Centre the map across both tunnels
    all_coords: List[List[float]] = []
    for t in tunnels:
        all_coords.extend(t.get("alignment", []))
    centre = _midpoint(all_coords)

    m = folium.Map(
        location=centre,
        zoom_start=13,
        tiles="OpenStreetMap",
        height=height,
    )

    # Tunnel alignments
    for t in tunnels:
        alignment = t.get("alignment", [])
        if len(alignment) < 2:
            continue
        colour = TUNNEL_COLOURS.get(t["tunnel_id"], "#666666")
        weight = 6 if t["tunnel_id"] == selected_tunnel_id else 4
        opacity = 1.0 if t["tunnel_id"] == selected_tunnel_id else 0.7

        folium.PolyLine(
            locations=alignment,
            color=colour,
            weight=weight,
            opacity=opacity,
            tooltip=(
                f"{t['label']} — {t['length_m']} m, "
                f"max depth {t.get('max_depth_m', '—')} m"
            ),
        ).add_to(m)

        # Portals
        for portal_key, portal in t.get("portals", {}).items():
            folium.CircleMarker(
                location=portal["coords"],
                radius=5,
                color=colour,
                fill=True,
                fill_opacity=1.0,
                tooltip=f"{t['label']} · {portal['label']}",
            ).add_to(m)

        # River crossings (Tunnel B has Yarra)
        for rx in t.get("river_crossings", []):
            folium.Marker(
                location=rx["approx_coords"],
                icon=folium.Icon(color="blue", icon="tint", prefix="fa"),
                tooltip=f"{rx['name']} · ~K{rx.get('approx_chainage_m', '?')}m",
            ).add_to(m)

    # Defect markers — derive a coordinate from each defect's chainage
    for d in defects:
        coords = _defect_coords(d, tunnels)
        if coords is None:
            continue
        priority = d.get("priority", "MEDIUM")
        colour = PRIORITY_COLOURS.get(priority, "#999999")
        popup_html = (
            f"<b>{d['defect_id']}</b><br>"
            f"{d.get('description', '')}<br>"
            f"<i>Ring {d.get('ring_id', '?')} · "
            f"K{d.get('chainage_m', 0):.0f}m</i><br>"
            f"Priority: <b>{priority}</b>"
        )
        folium.CircleMarker(
            location=coords,
            radius=7,
            color=colour,
            fill=True,
            fill_opacity=0.85,
            weight=2,
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=d["defect_id"],
        ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m


def build_ingest_map(
    selected_tunnel_id: str,
    selected_chainage: Optional[float] = None,
    height: int = 450,
) -> folium.Map:
    """
    Build the click-to-locate map for the Ingest page.

    Shows the selected tunnel prominently, the other tunnel faded.
    If `selected_chainage` is given, places a marker at that point along
    the alignment so the operator can see where they've already picked.
    """
    geom = load_tunnel_geometry()
    tunnels = geom.get("tunnels", [])
    selected = next(
        (t for t in tunnels if t["tunnel_id"] == selected_tunnel_id), None
    )

    if selected is None:
        return build_overview_map([], height=height)

    alignment = selected.get("alignment", [])
    centre = _midpoint(alignment) if alignment else (-37.82, 144.95)

    m = folium.Map(
        location=centre,
        zoom_start=14,
        tiles="OpenStreetMap",
        height=height,
    )

    # Other tunnels (faded)
    for t in tunnels:
        if t["tunnel_id"] == selected_tunnel_id:
            continue
        a = t.get("alignment", [])
        if len(a) >= 2:
            folium.PolyLine(
                locations=a,
                color=TUNNEL_COLOURS.get(t["tunnel_id"], "#999999"),
                weight=2,
                opacity=0.35,
                dash_array="4 8",
                tooltip=f"{t['label']} (not selected)",
            ).add_to(m)

    # Selected tunnel (prominent)
    if len(alignment) >= 2:
        colour = TUNNEL_COLOURS.get(selected_tunnel_id, "#1f78b4")
        folium.PolyLine(
            locations=alignment,
            color=colour,
            weight=6,
            opacity=1.0,
            tooltip=f"{selected['label']} — click anywhere along to locate",
        ).add_to(m)

        # Portals
        for portal_key, portal in selected.get("portals", {}).items():
            folium.Marker(
                location=portal["coords"],
                icon=folium.Icon(color="black", icon="info-sign"),
                tooltip=f"{selected['label']} · {portal['label']}",
            ).add_to(m)

        # River crossings
        for rx in selected.get("river_crossings", []):
            folium.Marker(
                location=rx["approx_coords"],
                icon=folium.Icon(color="blue", icon="tint", prefix="fa"),
                tooltip=f"{rx['name']} · ~K{rx.get('approx_chainage_m', '?')}m",
            ).add_to(m)

    # If the user has already picked a chainage, place a marker
    if selected_chainage is not None and len(alignment) >= 2:
        coords = _chainage_to_coords(
            selected_chainage, alignment, selected.get("ring_length_m", 1.6)
        )
        if coords is not None:
            folium.Marker(
                location=coords,
                icon=folium.Icon(color="red", icon="map-marker", prefix="fa"),
                tooltip=f"Picked location: K{selected_chainage:.0f}m",
            ).add_to(m)

    return m


# -----------------------------------------------------------------------------
# Reverse projection — chainage to coords, used to place defect markers
# -----------------------------------------------------------------------------
def _chainage_to_coords(
    chainage_m: float,
    alignment: List[List[float]],
    ring_length_m: float = 1.6,  # noqa: ARG001 (kept for API symmetry)
) -> Optional[Tuple[float, float]]:
    """
    Walk the alignment polyline until cumulative length matches chainage.
    Returns the (lat, lon) at that point, or None if chainage exceeds
    total length.
    """
    if not alignment or chainage_m < 0:
        return None
    cumulative = 0.0
    for i in range(len(alignment) - 1):
        a = tuple(alignment[i])
        b = tuple(alignment[i + 1])
        seg_len = haversine_m(a, b)
        if cumulative + seg_len >= chainage_m:
            t = (chainage_m - cumulative) / seg_len if seg_len > 0 else 0
            lat = a[0] + t * (b[0] - a[0])
            lon = a[1] + t * (b[1] - a[1])
            return (lat, lon)
        cumulative += seg_len
    # Past the end — return the final vertex
    return tuple(alignment[-1])


def _defect_coords(
    defect: Dict[str, Any],
    tunnels: List[Dict[str, Any]],
) -> Optional[Tuple[float, float]]:
    """
    Try to derive map coordinates for a defect.

    Priority:
    1. Explicit `coords` in the defect dict (if ever set)
    2. `tunnel_id` + `chainage_m` lookup against the alignment
    3. Heuristic: pick whichever tunnel's range plausibly contains the
       chainage value (back-compat for defects with no tunnel_id)
    """
    if "coords" in defect and defect["coords"]:
        c = defect["coords"]
        return (c[0], c[1])

    chainage = defect.get("chainage_m")
    if chainage is None:
        return None

    tunnel_id = defect.get("tunnel_id")
    if tunnel_id:
        for t in tunnels:
            if t["tunnel_id"] == tunnel_id:
                return _chainage_to_coords(
                    chainage,
                    t.get("alignment", []),
                    t.get("ring_length_m", 1.6),
                )

    # Back-compat: try whichever tunnel's range covers this chainage
    for t in tunnels:
        if 0 <= chainage <= t.get("length_m", 0):
            return _chainage_to_coords(
                chainage,
                t.get("alignment", []),
                t.get("ring_length_m", 1.6),
            )
    return None


# -----------------------------------------------------------------------------
# Position-zone helper — turn a click position into Crown/Springline/etc.
# -----------------------------------------------------------------------------
def position_from_offset(perp_offset_m: float) -> str:
    """
    Map a perpendicular offset distance (from the tunnel centreline)
    to a position-zone label.

    This is a coarse heuristic — for a proper Crown/Invert distinction
    you'd need 3D context the operator picks separately. Here we treat
    a click *on* the alignment as 'Crown' and offsets either side as
    'Sidewall'.
    """
    if perp_offset_m < 5:
        return "Crown"
    return "Sidewall"
