"""
BIM 3-D tunnel visualisation
============================

Builds an interactive plotly 3-D model of a tunnel: the lining as a
semi-transparent tube sized from the BIM as-built record (internal
diameter), reference ring hoops along the chainage axis, and every
defect plotted at its surveyed location — chainage along the tunnel,
circumferential angle from its position label ("Crown", "Left
sidewall lower", "Springline_R", ...).

Geometry note: a road tunnel is thousands of metres long but only
~7–14 m across, so a true-scale model degenerates into a hairline.
The scene uses a fixed 5:1:1 aspect box — chainage is compressed so
the cross-section stays readable. The page caption says so.
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


def position_to_angle_deg(position: str) -> float:
    """
    Map a free-text cross-section position to an angle in degrees.

    0° = crown (top), ±90° = springlines, ±125–150° = sidewalls,
    180° = invert. Left = negative, right = positive. Unknown labels
    park at +60° (upper right) rather than being dropped.
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


def build_tunnel_3d_figure(
    tunnel: Dict[str, Any],
    bim_tunnel: Optional[Dict[str, Any]],
    defects: List[Dict[str, Any]],
    colour_by: str = "priority",
) -> go.Figure:
    """
    Assemble the 3-D figure: lining tube + ring hoops + portal labels
    + one marker trace per colour group (so plotly's legend doubles as
    the colour key, and groups can be toggled by clicking it).
    """
    length = float(tunnel.get("length_m", 1000))
    diameter = float((bim_tunnel or {}).get("internal_diameter_m")
                     or DEFAULT_DIAMETER_M)
    r = diameter / 2.0
    ring_len = float(tunnel.get("ring_length_m", 1.6))
    rings_total = int(tunnel.get("rings_total") or (length / ring_len))

    fig = go.Figure()

    # Lining tube (semi-transparent so markers on the far side show)
    xs = np.linspace(0.0, length, 60)
    phis = np.linspace(0.0, 2 * np.pi, 49)
    fig.add_trace(go.Surface(
        x=np.outer(xs, np.ones_like(phis)),
        y=np.outer(np.ones_like(xs), r * np.sin(phis)),
        z=np.outer(np.ones_like(xs), r * np.cos(phis)),
        opacity=0.18,
        showscale=False,
        colorscale=[[0, "#8A84C8"], [1, "#8A84C8"]],
        hoverinfo="skip",
        name="Lining",
    ))

    # Ring hoops every ~1/7th of the tunnel, as spatial reference
    step = max(1, rings_total // 7)
    hoop_phi = np.linspace(0, 2 * np.pi, 49)
    for k in range(0, rings_total + 1, step):
        x0 = min(k * ring_len, length)
        fig.add_trace(go.Scatter3d(
            x=np.full_like(hoop_phi, x0),
            y=(r * 1.001) * np.sin(hoop_phi),
            z=(r * 1.001) * np.cos(hoop_phi),
            mode="lines",
            line=dict(color="#B9B5A8", width=2),
            hovertext=f"Ring {k} · K{x0:.0f}m",
            hoverinfo="text",
            showlegend=False,
        ))

    # Portal labels
    fig.add_trace(go.Scatter3d(
        x=[0, length], y=[0, 0], z=[r * 1.7, r * 1.7],
        mode="text",
        text=["West portal · K0", f"East portal · K{length:.0f}"],
        textfont=dict(size=12, color="#5F5E5A"),
        hoverinfo="skip",
        showlegend=False,
    ))

    # Defects, grouped so the legend is the colour key
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for d in defects:
        chainage = d.get("chainage_m")
        if not chainage or float(chainage) <= 0:
            continue
        if colour_by == "priority":
            key = d.get("priority") or "—"
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
            y, z = _on_surface(r + 0.4,
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
                d.get("position", "—"),
                d.get("ring_id", "?"),
                d.get("priority", "—"),
                (f"${d.get('estimated_cost_aud', 0):,.0f}"
                 if d.get("estimated_cost_aud") else "—"),
                (d.get("description", "") or "")[:70],
            ] for d in ds],
            hovertemplate=(
                "<b>%{customdata[0]}</b> — %{customdata[1]}<br>"
                "%{customdata[6]}<br>"
                "Ring %{customdata[3]} · K%{x:.0f}m · %{customdata[2]}<br>"
                "Priority %{customdata[4]} · Est. %{customdata[5]}"
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
