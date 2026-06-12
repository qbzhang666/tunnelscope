"""
Tunnel Setup — page 6
=====================

Lets the user register their own tunnel, so the app is not limited to
the built-in demo assets (Tunnels A and B).

Flow: name the tunnel → give its two portal coordinates (or paste a
full alignment polyline) → preview on a map → save. Saved tunnels go
to data/custom_tunnels.json, which utils/gis.py merges into
load_tunnel_geometry() — so a saved tunnel automatically appears in
the Ingest tunnel picker, the Defect Register map, the sidebar
selector, and the click-to-chainage resolver, with no other changes.

Tunnel length is measured from the alignment geometry (haversine sum)
so the map and the chainage system always agree; a manual override is
available for cases where the traced line is approximate.
"""

import folium
import streamlit as st
from streamlit.components.v1 import html as components_html

from utils.styling import apply_custom_css
from utils.explainers import render_plain_guide
from utils.gis import (
    list_tunnels, list_custom_tunnels, save_custom_tunnel,
    delete_custom_tunnel, haversine_m, _tunnel_colour,
)

apply_custom_css()

st.title("Tunnel setup")
st.caption(
    "Tunnels A and B are built-in demo assets. Register your own here — "
    "it then appears in every tunnel list and on every map, ready for "
    "defects to be logged against it."
)

render_plain_guide(
    "① Name the tunnel · ② enter its two portal coordinates (or paste "
    "an alignment) · ③ preview on the map · ④ **Save**. Then log "
    "defects against it on the **Ingest** page."
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _suggest_tunnel_id() -> str:
    """First free TUN-<letter> ID, starting from C (A and B are built-in)."""
    existing = {t["tunnel_id"] for t in list_tunnels()}
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        candidate = f"TUN-{letter}"
        if candidate not in existing:
            return candidate
    return "TUN-Z2"


def _parse_vertices(text: str):
    """Parse 'lat, lon' lines into [[lat, lon], ...]. Returns (points, errors)."""
    points, errors = [], []
    for i, raw in enumerate(text.strip().splitlines(), 1):
        line = raw.strip().strip("()[],")
        if not line:
            continue
        parts = [p for p in line.replace(",", " ").split() if p]
        if len(parts) != 2:
            errors.append(f"Line {i}: expected two numbers ('lat, lon').")
            continue
        try:
            lat, lon = float(parts[0]), float(parts[1])
        except ValueError:
            errors.append(f"Line {i}: not numeric.")
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            errors.append(f"Line {i}: latitude/longitude out of range.")
            continue
        points.append([lat, lon])
    return points, errors


def _polyline_length_m(points) -> float:
    return sum(
        haversine_m(tuple(points[i]), tuple(points[i + 1]))
        for i in range(len(points) - 1)
    )


def _build_preview_map(tunnel: dict, height: int = 380) -> folium.Map:
    """Selected-tunnel preview: new alignment plus the existing tunnels faded."""
    alignment = tunnel["alignment"]
    centre = (
        sum(p[0] for p in alignment) / len(alignment),
        sum(p[1] for p in alignment) / len(alignment),
    )
    m = folium.Map(location=centre, zoom_start=13, tiles="OpenStreetMap",
                   height=height)

    for t in list_tunnels():
        a = t.get("alignment", [])
        if len(a) >= 2:
            folium.PolyLine(
                locations=a, color=_tunnel_colour(t), weight=2,
                opacity=0.35, dash_array="4 8",
                tooltip=f"{t['label']} (existing)",
            ).add_to(m)

    folium.PolyLine(
        locations=alignment, color=tunnel.get("colour", "#534AB7"),
        weight=6, opacity=1.0, tooltip=f"{tunnel['label']} (new)",
    ).add_to(m)
    for key, portal in tunnel.get("portals", {}).items():
        folium.Marker(
            location=portal["coords"],
            icon=folium.Icon(color="black", icon="info-sign"),
            tooltip=portal["label"],
        ).add_to(m)
    return m


# -----------------------------------------------------------------------------
# Registration form
# -----------------------------------------------------------------------------
with st.form("tunnel_setup_form"):
    col1, col2 = st.columns(2)
    with col1:
        label = st.text_input(
            "Tunnel name",
            value="",
            placeholder="e.g. Tunnel C — Northbound",
        )
    with col2:
        tunnel_id = st.text_input(
            "Tunnel ID",
            value=_suggest_tunnel_id(),
            help="Short unique code stored on every defect record.",
        )

    col3, col4 = st.columns(2)
    with col3:
        ring_length_m = st.number_input(
            "Ring length (m)", min_value=0.5, max_value=5.0,
            value=1.6, step=0.1,
            help="Length of one lining ring. Ring numbers are derived "
                 "from chainage using this.",
        )
    with col4:
        max_depth_m = st.number_input(
            "Max depth (m)", min_value=0, max_value=200, value=25,
        )

    st.markdown("**Alignment** — where the tunnel runs")
    st.caption(
        "Enter the two portal coordinates (decimal degrees, from any "
        "online map). The alignment is drawn as a straight line between "
        "them — paste more vertices under *Advanced* for a curved route."
    )
    colw, cole = st.columns(2)
    with colw:
        st.markdown("West / start portal")
        west_lat = st.number_input("Latitude (start)", value=-37.83000,
                                   format="%.5f", step=0.001)
        west_lon = st.number_input("Longitude (start)", value=144.92000,
                                   format="%.5f", step=0.001)
    with cole:
        st.markdown("East / end portal")
        east_lat = st.number_input("Latitude (end)", value=-37.81500,
                                   format="%.5f", step=0.001)
        east_lon = st.number_input("Longitude (end)", value=144.95500,
                                   format="%.5f", step=0.001)

    with st.expander("Advanced — full alignment and length override"):
        vertices_text = st.text_area(
            "Alignment vertices (one 'lat, lon' per line — overrides "
            "the portal fields above)",
            value="",
            height=120,
            placeholder="-37.8300, 144.9200\n-37.8250, 144.9350\n-37.8150, 144.9550",
        )
        length_override_m = st.number_input(
            "Length override (m) — 0 = use the measured alignment length",
            min_value=0.0, value=0.0, step=100.0,
        )

    preview_clicked = st.form_submit_button("Preview on map")
    save_clicked = st.form_submit_button("Save tunnel", type="primary")

# -----------------------------------------------------------------------------
# Build + validate the tunnel from the form values
# -----------------------------------------------------------------------------
if preview_clicked or save_clicked:
    problems = []

    if vertices_text.strip():
        alignment, parse_errors = _parse_vertices(vertices_text)
        problems.extend(parse_errors)
        if len(alignment) < 2:
            problems.append("Need at least two valid alignment vertices.")
    else:
        alignment = [[west_lat, west_lon], [east_lat, east_lon]]

    if not label.strip():
        problems.append("Give the tunnel a name.")

    measured_m = _polyline_length_m(alignment) if len(alignment) >= 2 else 0.0
    length_m = length_override_m if length_override_m > 0 else measured_m
    if length_m <= 0:
        problems.append(
            "Tunnel length is zero — the start and end coordinates are "
            "identical."
        )

    if problems:
        for p in problems:
            st.error(p)
    else:
        tunnel = {
            "tunnel_id": tunnel_id.strip(),
            "label": label.strip(),
            "length_m": round(length_m),
            "rings_total": int(length_m / ring_length_m),
            "ring_length_m": ring_length_m,
            "max_depth_m": max_depth_m,
            "alignment": alignment,
            "portals": {
                "west": {"coords": alignment[0],
                         "label": f"{label.strip()} — start portal"},
                "east": {"coords": alignment[-1],
                         "label": f"{label.strip()} — end portal"},
            },
        }

        st.caption(
            f"Measured alignment length: **{measured_m:,.0f} m**"
            + (f" · using override **{length_override_m:,.0f} m**"
               if length_override_m > 0 else "")
            + f" · ≈ **{tunnel['rings_total']:,} rings** at "
              f"{ring_length_m} m/ring"
        )
        components_html(_build_preview_map(tunnel)._repr_html_(), height=400)

        if save_clicked:
            ok, msg = save_custom_tunnel(tunnel)
            if ok:
                st.success(
                    f"✅ {msg} It is now available on the **Ingest** page "
                    f"(to log defects), the **Defect Register** map, and "
                    f"the sidebar tunnel selector."
                )
            else:
                st.error(msg)

# -----------------------------------------------------------------------------
# Manage existing tunnels
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Your tunnels")

built_in = [t for t in list_tunnels() if not t.get("custom")]
st.caption(
    "Built-in (demo, can't be deleted): "
    + " · ".join(f"{t['label']} ({t['tunnel_id']})" for t in built_in)
)

customs = list_custom_tunnels()
if not customs:
    st.info("No custom tunnels yet — register one above.")
else:
    for t in customs:
        col1, col2, col3, col4 = st.columns([2, 4, 3, 2])
        with col1:
            st.code(t["tunnel_id"], language=None)
        with col2:
            st.markdown(f"**{t['label']}**")
        with col3:
            st.caption(
                f"{t.get('length_m', 0):,} m · "
                f"{t.get('rings_total', 0):,} rings · "
                f"max depth {t.get('max_depth_m', '—')} m"
            )
        with col4:
            if st.button(f"Delete {t['tunnel_id']}",
                         key=f"delete_{t['tunnel_id']}"):
                delete_custom_tunnel(t["tunnel_id"])
                st.rerun()
