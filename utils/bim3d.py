"""
BIM 3-D tunnel visualisation
============================

Builds an interactive plotly 3-D model of a precast-segmental tunnel
lining and plots every defect at its surveyed location.

Unlike a plain tube, the lining is modelled from the BIM as-built
record the way it is actually built:

  * internal diameter and **lining thickness** -> an inner bore surface,
    an outer extrados surface and annular **end caps**, so the shell
    thickness is visible;
  * **segments per ring** -> longitudinal radial joints dividing the
    ring into segments of equal arc, plus one narrower **keystone** at
    the crown (highlighted);
  * **ring length** -> circumferential ring joints (hoops) along the
    chainage axis.

All of these come straight from `data/bim_as_built.json`
(`internal_diameter_m`, `lining_thickness_m`, `segments_per_ring`,
`ring_length_m`); the page lets the user override them for tunnels
that have no as-built record yet.

Geometry note: a road tunnel is thousands of metres long but only
~7-14 m across, so a true-scale model degenerates into a hairline.
The 3-D scene uses a fixed 5:1:1 aspect box - chainage is compressed
so the cross-section stays readable - and a separate **true-scale 2-D
cross-section** (`build_ring_section_figure`) shows the ring geometry
without distortion.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import plotly.graph_objects as go

from utils.gis import PRIORITY_COLOURS

# Colour cycle for the "colour by defect type" mode.
TYPE_PALETTE = [
    "#1f78b4", "#e31a1c", "#33a02c", "#ff7f0e",
    "#6a3d9a", "#b15928", "#0e7c7b", "#e07b39",
]

DEFAULT_DIAMETER_M = 7.0
DEFAULT_LINING_THICKNESS_M = 0.4
DEFAULT_SEGMENTS_PER_RING = 7
# The keystone's arc as a fraction of a standard segment's arc (a real
# key is a narrow wedge driven in last). 0.4 is typical.
DEFAULT_KEYSTONE_RATIO = 0.4

LINING_COLOUR = "#8A84C8"
KEYSTONE_COLOUR = "#E8A33D"
JOINT_COLOUR = "#6F6A9C"


def position_to_angle_deg(position: str) -> float:
    """
    Map a free-text cross-section position to an angle in degrees.

    0 deg = crown (top), +/-90 deg = springlines, +/-125-150 deg =
    sidewalls, 180 deg = invert. Left = negative, right = positive.
    Unknown labels park at +60 deg (upper right) rather than dropped.
    """
    p = f" {(position or '').lower().replace('_', ' ').replace('-', ' ').strip()} "
    left = " left " in p or p.endswith(" l ")
    if "crown" in p:
        return 0.0
    if "invert" in p:
        return 180.0
    if "springline" in p:
        return -90.0 if left else 90.0
    if "sidewall" in p:
        base = 150.0 if "lower" in p else 125.0
        return -base if left else base
    if "shoulder" in p:
        return -45.0 if left else 45.0
    return 60.0


def _on_surface(r: float, angle_deg: float) -> Tuple[float, float]:
    """(y, z) on the lining at a given clock angle from the crown."""
    phi = math.radians(angle_deg)
    return r * math.sin(phi), r * math.cos(phi)


# -----------------------------------------------------------------------------
# Segmental-ring geometry
# -----------------------------------------------------------------------------
def ring_segment_boundaries(
    segments_per_ring: int,
    keystone_ratio: float = DEFAULT_KEYSTONE_RATIO,
    rotation_deg: float = 0.0,
) -> List[Tuple[float, float, bool]]:
    """
    Boundary angles (deg from crown) for one ring's segments.

    One narrow keystone is centred on the crown (0 deg); the remaining
    (n-1) segments share the rest of the circle in equal arcs. Returns
    a list of (start_deg, end_deg, is_keystone), proceeding clockwise,
    optionally rotated by `rotation_deg` (used to stagger successive
    rings).

    Arc maths: std*(n-1) + std*ratio = 360  ->  std = 360/((n-1)+ratio)
    """
    n = max(3, int(segments_per_ring))
    std = 360.0 / ((n - 1) + keystone_ratio)
    key = std * keystone_ratio
    bounds: List[Tuple[float, float, bool]] = []
    a = -key / 2.0           # keystone centred on the crown
    bounds.append((a, a + key, True))
    a += key
    for _ in range(n - 1):
        bounds.append((a, a + std, False))
        a += std
    return [(s + rotation_deg, e + rotation_deg, k) for s, e, k in bounds]


def _tube_surface(length: float, r: float, opacity: float,
                  color: str, name: str, n_x: int = 60,
                  n_phi: int = 49) -> go.Surface:
    """A semi-transparent cylinder of radius `r` along the x-axis."""
    xs = np.linspace(0.0, length, n_x)
    phis = np.linspace(0.0, 2 * np.pi, n_phi)
    return go.Surface(
        x=np.outer(xs, np.ones_like(phis)),
        y=np.outer(np.ones_like(xs), r * np.sin(phis)),
        z=np.outer(np.ones_like(xs), r * np.cos(phis)),
        opacity=opacity,
        showscale=False,
        colorscale=[[0, color], [1, color]],
        hoverinfo="skip",
        name=name,
        showlegend=False,
    )


def _annulus_endcap(x: float, r_in: float, r_out: float,
                    color: str, n: int = 64) -> go.Mesh3d:
    """A filled ring (annulus) in the y-z plane at chainage `x`, so the
    shell thickness reads as a solid face at the portal."""
    phis = np.linspace(0.0, 2 * np.pi, n)
    ys = np.concatenate([r_in * np.sin(phis), r_out * np.sin(phis)])
    zs = np.concatenate([r_in * np.cos(phis), r_out * np.cos(phis)])
    xs = np.full(2 * n, x)
    i, j, k = [], [], []
    for m in range(n - 1):
        inner_a, inner_b = m, m + 1
        outer_a, outer_b = n + m, n + m + 1
        i += [inner_a, inner_b]      # two triangles per quad strip
        j += [inner_b, outer_b]
        k += [outer_a, outer_a]
    return go.Mesh3d(
        x=xs, y=ys, z=zs, i=i, j=j, k=k,
        color=color, opacity=0.55, hoverinfo="skip",
        name="Lining thickness", showlegend=False,
    )


# -----------------------------------------------------------------------------
# 3-D figure
# -----------------------------------------------------------------------------
def build_tunnel_3d_figure(
    tunnel: Dict[str, Any],
    bim_tunnel: Optional[Dict[str, Any]],
    defects: List[Dict[str, Any]],
    colour_by: str = "priority",
    *,
    segments_per_ring: Optional[int] = None,
    lining_thickness_m: Optional[float] = None,
    keystone_ratio: float = DEFAULT_KEYSTONE_RATIO,
    show_segments: bool = True,
) -> go.Figure:
    """
    Assemble the 3-D figure: a segmental lining shell (inner bore +
    outer extrados + annular end caps), longitudinal radial joints with
    a highlighted keystone, ring-joint hoops, portal labels, and one
    marker trace per colour group (so plotly's legend doubles as the
    colour key).

    Lining parameters default to the BIM as-built record; pass
    `segments_per_ring` / `lining_thickness_m` to override (used by the
    page's geometry controls for tunnels with no as-built record).
    """
    length = float(tunnel.get("length_m", 1000))
    diameter = float((bim_tunnel or {}).get("internal_diameter_m")
                     or DEFAULT_DIAMETER_M)
    r_in = diameter / 2.0
    thickness = float(
        lining_thickness_m
        if lining_thickness_m is not None
        else (bim_tunnel or {}).get("lining_thickness_m")
        or DEFAULT_LINING_THICKNESS_M
    )
    r_out = r_in + thickness
    n_seg = int(
        segments_per_ring
        if segments_per_ring is not None
        else (bim_tunnel or {}).get("segments_per_ring")
        or DEFAULT_SEGMENTS_PER_RING
    )
    ring_len = float(tunnel.get("ring_length_m", 1.6))
    rings_total = int(tunnel.get("rings_total") or (length / ring_len))

    fig = go.Figure()

    # --- Lining shell: inner bore (markers sit just outside it), faint
    #     outer extrados, and solid annular end caps for the thickness.
    fig.add_trace(_tube_surface(length, r_in, 0.16, LINING_COLOUR, "Bore"))
    fig.add_trace(_tube_surface(length, r_out, 0.09, LINING_COLOUR, "Extrados"))
    fig.add_trace(_annulus_endcap(0.0, r_in, r_out, LINING_COLOUR))
    fig.add_trace(_annulus_endcap(length, r_in, r_out, LINING_COLOUR))

    # --- Ring joints (hoops) every ~1/12 of the tunnel, as reference.
    step = max(1, rings_total // 12)
    hoop_phi = np.linspace(0, 2 * np.pi, 49)
    for kk in range(0, rings_total + 1, step):
        x0 = min(kk * ring_len, length)
        fig.add_trace(go.Scatter3d(
            x=np.full_like(hoop_phi, x0),
            y=(r_out * 1.001) * np.sin(hoop_phi),
            z=(r_out * 1.001) * np.cos(hoop_phi),
            mode="lines",
            line=dict(color="#B9B5A8", width=2),
            hovertext=f"Ring {kk} - K{x0:.0f}m",
            hoverinfo="text",
            showlegend=False,
        ))

    # --- Longitudinal radial joints + keystone strip (segmentation).
    if show_segments:
        bounds = ring_segment_boundaries(n_seg, keystone_ratio)
        edge_angles = sorted({round(s, 4) for s, _, _ in bounds})
        for ang in edge_angles:
            y, z = _on_surface(r_out * 1.002, ang)
            fig.add_trace(go.Scatter3d(
                x=[0, length], y=[y, y], z=[z, z],
                mode="lines",
                line=dict(color=JOINT_COLOUR, width=2),
                hoverinfo="skip", showlegend=False,
            ))
        # Keystone running strip at the crown.
        ks, ke, _ = bounds[0]
        key_phi = np.linspace(math.radians(ks), math.radians(ke), 8)
        kx = np.linspace(0, length, 30)
        fig.add_trace(go.Surface(
            x=np.outer(kx, np.ones_like(key_phi)),
            y=np.outer(np.ones_like(kx), (r_out * 1.003) * np.sin(key_phi)),
            z=np.outer(np.ones_like(kx), (r_out * 1.003) * np.cos(key_phi)),
            opacity=0.55, showscale=False,
            colorscale=[[0, KEYSTONE_COLOUR], [1, KEYSTONE_COLOUR]],
            hoverinfo="skip", name="Keystone", showlegend=False,
        ))

    # --- Portal labels.
    fig.add_trace(go.Scatter3d(
        x=[0, length], y=[0, 0], z=[r_out * 1.7, r_out * 1.7],
        mode="text",
        text=["West portal - K0", f"East portal - K{length:.0f}"],
        textfont=dict(size=12, color="#5F5E5A"),
        hoverinfo="skip", showlegend=False,
    ))

    # --- Defects, grouped so the legend is the colour key.
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for d in defects:
        chainage = d.get("chainage_m")
        if not chainage or float(chainage) <= 0:
            continue
        if colour_by == "priority":
            key = d.get("priority") or "-"
        else:
            key = d.get("defect_type") or "Unclassified"
        groups.setdefault(key, []).append(d)

    type_colours = {key: TYPE_PALETTE[i % len(TYPE_PALETTE)]
                    for i, key in enumerate(sorted(groups))}

    for key in sorted(groups):
        ds = groups[key]
        if colour_by == "priority":
            colour = PRIORITY_COLOURS.get(key, "#999999")
        else:
            colour = type_colours[key]
        ys, zs = [], []
        for d in ds:
            y, z = _on_surface(r_in + 0.4,
                               position_to_angle_deg(d.get("position", "")))
            ys.append(y)
            zs.append(z)
        fig.add_trace(go.Scatter3d(
            x=[min(float(d["chainage_m"]), length) for d in ds],
            y=ys,
            z=zs,
            mode="markers",
            marker=dict(size=7, color=colour,
                        line=dict(width=1, color="#FFFFFF")),
            name=f"{key} ({len(ds)})",
            customdata=[[
                d.get("defect_id", ""),
                d.get("defect_type", ""),
                d.get("position", "-"),
                d.get("ring_id", "?"),
                d.get("priority", "-"),
                (f"${d.get('estimated_cost_aud', 0):,.0f}"
                 if d.get("estimated_cost_aud") else "-"),
                (d.get("description", "") or "")[:70],
            ] for d in ds],
            hovertemplate=(
                "<b>%{customdata[0]}</b> - %{customdata[1]}<br>"
                "%{customdata[6]}<br>"
                "Ring %{customdata[3]} - K%{x:.0f}m - %{customdata[2]}<br>"
                "Priority %{customdata[4]} - Est. %{customdata[5]}"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(
        scene=dict(
            aspectmode="manual",
            aspectratio=dict(x=5, y=1, z=1),
            xaxis=dict(title="Chainage (m)", color="#5F5E5A",
                       showbackground=False),
            yaxis=dict(visible=False),
            zaxis=dict(visible=False),
            camera=dict(eye=dict(x=1.7, y=1.3, z=0.7)),
        ),
        height=520,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=0.02, x=0.02,
                    bgcolor="rgba(255,255,255,0.6)"),
    )
    return fig


# -----------------------------------------------------------------------------
# True-scale 2-D cross-section (un-distorted ring geometry)
# -----------------------------------------------------------------------------
def _arc_xy(r: float, a0: float, a1: float, n: int = 40):
    """Points along an arc from a0..a1 deg (from crown), x=r sin, y=r cos."""
    angs = np.radians(np.linspace(a0, a1, n))
    return r * np.sin(angs), r * np.cos(angs)


def build_ring_section_figure(
    diameter_m: float,
    thickness_m: float,
    segments_per_ring: int,
    keystone_ratio: float = DEFAULT_KEYSTONE_RATIO,
    defects: Optional[List[Dict[str, Any]]] = None,
) -> go.Figure:
    """
    A true-scale cross-section of one ring, looking down the tunnel
    axis: inner bore, outer extrados, every radial joint, the keystone
    wedge filled, and (optionally) defects placed at their circumfer-
    ential angle. This is where thickness, segment count, segment arc
    width and the keystone read clearly, because nothing is compressed.
    """
    r_in = diameter_m / 2.0
    r_out = r_in + thickness_m
    fig = go.Figure()

    # Inner and outer circles.
    for r, col, w in ((r_in, "#5F5E5A", 2), (r_out, LINING_COLOUR, 3)):
        xs, ys = _arc_xy(r, 0, 360, 180)
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
                                 line=dict(color=col, width=w),
                                 hoverinfo="skip", showlegend=False))

    bounds = ring_segment_boundaries(segments_per_ring, keystone_ratio)

    # Keystone wedge (filled): inner arc -> outer arc -> close.
    ks, ke, _ = bounds[0]
    xi, yi = _arc_xy(r_in, ks, ke)
    xo, yo = _arc_xy(r_out, ke, ks)
    fig.add_trace(go.Scatter(
        x=np.concatenate([xi, xo]), y=np.concatenate([yi, yo]),
        fill="toself", mode="lines",
        line=dict(color=KEYSTONE_COLOUR, width=1),
        fillcolor="rgba(232,163,61,0.45)",
        hovertext="Keystone (K)", hoverinfo="text", showlegend=False,
    ))

    # Radial joints + segment labels.
    std_arc_deg = (360.0 - (ke - ks)) / max(1, (segments_per_ring - 1))
    seg_arc_m = math.radians(std_arc_deg) * (r_in + thickness_m / 2.0)
    for idx, (s, e, is_key) in enumerate(bounds):
        x0, y0 = _on_surface(r_in, s)
        x1, y1 = _on_surface(r_out, s)
        fig.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines",
                                 line=dict(color=JOINT_COLOUR, width=2),
                                 hoverinfo="skip", showlegend=False))
        mid = (s + e) / 2.0
        lx, ly = _on_surface((r_in + r_out) / 2.0, mid)
        fig.add_trace(go.Scatter(
            x=[lx], y=[ly], mode="text",
            text=["K" if is_key else str(idx)],
            textfont=dict(size=11,
                          color=KEYSTONE_COLOUR if is_key else "#5F5E5A"),
            hoverinfo="skip", showlegend=False,
        ))

    # Optional defects on the ring face.
    for d in (defects or []):
        ang = position_to_angle_deg(d.get("position", ""))
        dx, dy = _on_surface(r_in + thickness_m / 2.0, ang)
        fig.add_trace(go.Scatter(
            x=[dx], y=[dy], mode="markers",
            marker=dict(size=9, color=PRIORITY_COLOURS.get(
                d.get("priority"), "#999999"),
                line=dict(width=1, color="#FFFFFF")),
            hovertext=(f"{d.get('defect_id', '')} - "
                       f"{d.get('defect_type', '')} ({d.get('position', '-')})"),
            hoverinfo="text", showlegend=False,
        ))

    n_key = sum(1 for *_, k in bounds if k)
    title = (f"{segments_per_ring} segments/ring "
             f"({segments_per_ring - n_key} standard + {n_key} key) - "
             f"{diameter_m:.1f} m bore, {thickness_m*1000:.0f} mm lining - "
             f"standard segment {std_arc_deg:.0f}deg ~ {seg_arc_m:.2f} m arc")
    lim = r_out * 1.15
    fig.update_layout(
        title=dict(text=title, font=dict(size=12, color="#5F5E5A"), x=0.0),
        xaxis=dict(visible=False, range=[-lim, lim]),
        yaxis=dict(visible=False, range=[-lim, lim],
                   scaleanchor="x", scaleratio=1),  # true 1:1 aspect
        height=420,
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig
