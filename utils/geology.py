"""
Geology utilities — geological context lookup
=============================================

Loads `data/geological_context.json` and resolves a defect's chainage
to the geological zone and the layered stratigraphy at that point.
Also renders a matplotlib SVG cross-section showing strata above and
below the tunnel at the defect's chainage with a marker.

Used by:
    - pages/2_Defect_Detail.py — inline geology badge near the FMEA
      chain Component step (alongside the BIM badge), with full
      zone/stratigraphy details + cross-section diagram in an
      expandable section directly underneath.

DESIGN NOTES
------------
1. Two complementary representations:
   - zones_along_chainage: which geological zone the tunnel passes
     through at this chainage (e.g. 'Yarra crossing — deep Silurian
     Melbourne Formation'). Tunnel-substrate scale.
   - stratigraphy_at_chainage_samples: vertical column of layers
     above and below the tunnel at sample chainages. Used for the
     cross-section diagram. Interpolated when the defect's chainage
     falls between samples.
2. Rendering uses matplotlib in 'Agg' mode (no GUI) and emits SVG
   strings that Streamlit displays via st.image / st.markdown. Avoids
   the file-handle overhead of saving PNGs.
3. The hazards list per zone feeds a sidebar caveat on Defect Detail
   (per the user's choice — present, don't modify the FMEA chain).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
GEO_FILE = DATA_DIR / "geological_context.json"


# -----------------------------------------------------------------------------
# Loading
# -----------------------------------------------------------------------------
def load_geological_context() -> Dict[str, Any]:
    """Load the geological context JSON. Returns empty stub if missing."""
    if not GEO_FILE.exists():
        return {"_meta": {}, "tunnels": {}}
    try:
        with open(GEO_FILE) as f:
            return json.load(f)
    except Exception:
        return {"_meta": {}, "tunnels": {}}


def is_demonstration_data() -> bool:
    geo = load_geological_context()
    return bool(geo.get("_meta", {}).get("demonstration_data"))


def get_tunnel_record(tunnel_id: str) -> Optional[Dict[str, Any]]:
    geo = load_geological_context()
    return geo.get("tunnels", {}).get(tunnel_id)


# -----------------------------------------------------------------------------
# Zone lookup — which geological zone contains this chainage
# -----------------------------------------------------------------------------
def find_zone_for_chainage(
    tunnel_id: str,
    chainage_m: Optional[float],
) -> Optional[Dict[str, Any]]:
    """Return the geological zone that contains the given chainage."""
    if chainage_m is None:
        return None
    tunnel = get_tunnel_record(tunnel_id)
    if not tunnel:
        return None
    for zone in tunnel.get("zones_along_chainage", []):
        c_lo, c_hi = zone.get("chainage_range_m", [0, 0])
        if c_lo <= chainage_m <= c_hi:
            return zone
    return None


# -----------------------------------------------------------------------------
# Stratigraphy lookup — nearest sample to the defect's chainage
# -----------------------------------------------------------------------------
def find_nearest_stratigraphy(
    tunnel_id: str,
    chainage_m: Optional[float],
) -> Optional[Dict[str, Any]]:
    """
    Find the stratigraphic sample closest to the defect's chainage.

    We don't try to interpolate layer boundaries between two samples
    because that would imply more precision than the data warrants.
    The closest sample is presented honestly with a 'sampled at K{x}m,
    defect at K{y}m' caption in the UI.
    """
    if chainage_m is None:
        return None
    tunnel = get_tunnel_record(tunnel_id)
    if not tunnel:
        return None
    samples = tunnel.get("stratigraphy_at_chainage_samples", [])
    if not samples:
        return None
    nearest = min(
        samples,
        key=lambda s: abs(s.get("sample_chainage_m", 0) - chainage_m),
    )
    return nearest


# -----------------------------------------------------------------------------
# Convenience: assemble all geology context for a defect
# -----------------------------------------------------------------------------
def get_geology_context(defect: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pull together everything Defect Detail needs to render the geology
    badge + expandable section.
    """
    tunnel_id = defect.get("tunnel_id")
    chainage_m = defect.get("chainage_m")

    tunnel = get_tunnel_record(tunnel_id) if tunnel_id else None
    zone = (
        find_zone_for_chainage(tunnel_id, chainage_m)
        if tunnel_id else None
    )
    strat = (
        find_nearest_stratigraphy(tunnel_id, chainage_m)
        if tunnel_id else None
    )

    return {
        "tunnel": tunnel,
        "zone": zone,
        "stratigraphy": strat,
        "is_demo_data": is_demonstration_data(),
        "chainage_in_range": zone is not None,
    }


# -----------------------------------------------------------------------------
# Cross-section diagram (matplotlib → SVG string)
# -----------------------------------------------------------------------------
def build_cross_section_svg(
    stratigraphy: Dict[str, Any],
    defect_chainage_m: float,
    tunnel_diameter_m: float = 11.0,
    figure_height_in: float = 5.5,
    figure_width_in: float = 7.0,
) -> str:
    """
    Render an SVG cross-section showing strata at the defect's chainage,
    with the tunnel cross-section and a defect marker.

    Y-axis: depth below ground level, m
    X-axis: lateral position relative to tunnel centreline, m

    Returns the SVG as a string. Emit-then-close pattern; no file is
    written.
    """
    layers: List[Dict[str, Any]] = stratigraphy.get("layers", [])
    sample_chainage = stratigraphy.get("sample_chainage_m", 0)
    tunnel_depth = stratigraphy.get("tunnel_centreline_depth_m", 20)
    water_table_depth = stratigraphy.get("water_table_depth_m")
    ground_level_AHD = stratigraphy.get("ground_level_m_AHD")

    if not layers:
        return ""

    # Bounds — show 30 m laterally (15 m each side) for context
    x_lo, x_hi = -15, 15
    max_depth = max(
        layer.get("bottom_depth_m", 0) for layer in layers
    )
    max_depth = max(max_depth, tunnel_depth + tunnel_diameter_m / 2 + 3)

    fig, ax = plt.subplots(
        figsize=(figure_width_in, figure_height_in), dpi=110
    )

    # Strata as horizontal bands
    for layer in layers:
        top = layer.get("top_depth_m", 0)
        bottom = layer.get("bottom_depth_m", 0)
        colour = layer.get("colour", "#bbbbbb")
        unit = layer.get("unit", "Unknown")
        rect = Rectangle(
            (x_lo, top), x_hi - x_lo, bottom - top,
            facecolor=colour, edgecolor="#444", linewidth=0.5, alpha=0.85,
        )
        ax.add_patch(rect)
        # Label
        mid = (top + bottom) / 2
        if bottom - top > 1.5:  # only label thick enough layers
            ax.text(
                x_hi - 0.4, mid, unit,
                ha="right", va="center", fontsize=8,
                color="#222", weight="medium",
                bbox=dict(boxstyle="round,pad=0.15",
                          facecolor="white", edgecolor="none", alpha=0.7),
            )

    # Water table line — only annotate inside the chart if it doesn't
    # collide with the ground-level annotation
    if water_table_depth is not None and water_table_depth >= 0:
        ax.axhline(
            water_table_depth, color="#1f77b4", linewidth=1.4,
            linestyle="--", alpha=0.85,
        )
        # Place water table label lower (offset by 0.8 m below the line)
        # to avoid the ground level annotation at -0.5 m
        wt_label_y = water_table_depth + 0.9
        ax.text(
            x_lo + 0.4, wt_label_y,
            f"▽ water table ({water_table_depth:.1f} m)",
            color="#1f77b4", fontsize=8, weight="bold",
        )

    # Tunnel cross-section — circle centred on tunnel_depth
    tunnel_circle = plt.Circle(
        (0, tunnel_depth),
        tunnel_diameter_m / 2,
        edgecolor="#222", facecolor="#f0f0f0", linewidth=2.0, zorder=4,
    )
    ax.add_patch(tunnel_circle)
    ax.text(
        0, tunnel_depth, "TUNNEL",
        ha="center", va="center",
        fontsize=9, color="#333", weight="bold", zorder=5,
    )

    # Defect marker — red circle on the tunnel circumference (crown for now)
    ax.plot(
        0, tunnel_depth - tunnel_diameter_m / 2,
        marker="o", markersize=10, color="#d62728",
        markeredgecolor="white", markeredgewidth=1.5, zorder=6,
    )
    ax.annotate(
        "Defect",
        xy=(0, tunnel_depth - tunnel_diameter_m / 2),
        xytext=(4.5, tunnel_depth - tunnel_diameter_m / 2 - 2),
        fontsize=9, color="#d62728", weight="bold",
        arrowprops=dict(arrowstyle="->", color="#d62728", lw=1.2),
        zorder=7,
    )

    # Ground level annotation
    if ground_level_AHD is not None:
        ax.text(
            x_lo + 0.4, -0.5,
            f"Ground level (≈ {ground_level_AHD} m AHD)",
            fontsize=8, color="#555",
        )

    # Axes
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(max_depth, -2)  # invert: 0 at top
    ax.set_xlabel("Lateral distance from tunnel centreline (m)", fontsize=9)
    ax.set_ylabel("Depth below ground level (m)", fontsize=9)
    ax.set_title(
        f"Geological cross-section at K{sample_chainage}m "
        f"(defect at K{defect_chainage_m:.0f}m)",
        fontsize=10, weight="bold", pad=10,
    )
    ax.grid(True, alpha=0.25, linewidth=0.5)
    ax.tick_params(labelsize=8)

    plt.tight_layout()

    # Render to SVG string
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    svg_text = buf.getvalue()

    # Strip the XML prelude and DOCTYPE so the SVG can be embedded
    # directly inline in HTML via st.markdown(unsafe_allow_html=True).
    # Without stripping, browsers reject the embedded prelude.
    svg_start = svg_text.find("<svg")
    if svg_start > 0:
        svg_text = svg_text[svg_start:]
    return svg_text


# -----------------------------------------------------------------------------
# Hazard caveat — short cause-relevant note for the FMEA sidebar
# -----------------------------------------------------------------------------
def get_geology_cause_caveat(
    defect: Dict[str, Any],
) -> Optional[str]:
    """
    Return a short factual caveat about geological hazards at this
    defect's chainage, suitable for display next to (not inside) the
    Cause step of the FMEA chain.

    Per the user's design choice: geology informs but does NOT modify
    the inferred cause. The caveat is presented as a separate sidebar
    note the operator can read alongside the chain.
    """
    ctx = get_geology_context(defect)
    zone = ctx.get("zone")
    if not zone:
        return None

    hazards = zone.get("hazards", [])
    if not hazards:
        return None

    # Build a short, factual statement
    parts = [
        f"Geological context at K{defect.get('chainage_m', 0):.0f}m "
        f"({zone.get('name', 'this zone')}):"
    ]

    parts.append(
        f"substrate {zone.get('tunnel_substrate', 'unknown')}"
    )
    wt = zone.get("tunnel_depth_below_water_table_m")
    if wt is not None and wt > 0:
        parts.append(f"~{wt:.0f} m below water table")
    elif wt is not None and wt <= 0:
        parts.append("above water table")

    notes = zone.get("engineering_notes")
    hazards_str = "; ".join(hazards)

    caveat = (
        f"**{parts[0]}** {parts[1]}, {parts[2] if len(parts) > 2 else ''}.\n\n"
        f"**Documented hazards in this zone:** {hazards_str}.\n\n"
    )
    if notes:
        caveat += f"**Engineering notes:** {notes}"

    return caveat
