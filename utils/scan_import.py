"""
Scan-to-BIM model import
=========================

Parse an uploaded as-built model - a surface **mesh** (OBJ / STL / PLY)
or a **point cloud** (XYZ / PTS / CSV / PLY) from laser scanning or
photogrammetry - into vertices (+ faces) and a true-scale plotly figure.

Deliberately dependency-free: pure-Python / numpy parsers, so it runs in
the same environment as the app with nothing extra to install (unlike
full IFC geometry, which would need ifcopenshell). Point clouds are
subsampled for responsiveness; very large meshes fall back to their
vertex cloud.

Coordinates are shown in the scan's own frame, true scale. Defects are
not overlaid, because the scan and the digital-twin chainage frame are
not registered to one another (that would need a survey transform).
"""

from __future__ import annotations

import io
import struct
from typing import Any, Dict, Optional, Tuple

import numpy as np
import plotly.graph_objects as go

SUPPORTED_EXT = ("obj", "stl", "ply", "xyz", "pts", "csv", "txt")

MAX_POINTS = 60_000     # subsample cap for point clouds / large-mesh fallback
MAX_FACES = 250_000     # above this, render vertices as a point cloud instead

# PLY scalar type -> (struct char, byte size)
_PLY_T = {
    "char": ("b", 1), "uchar": ("B", 1), "int8": ("b", 1), "uint8": ("B", 1),
    "short": ("h", 2), "ushort": ("H", 2), "int16": ("h", 2), "uint16": ("H", 2),
    "int": ("i", 4), "uint": ("I", 4), "int32": ("i", 4), "uint32": ("I", 4),
    "float": ("f", 4), "float32": ("f", 4), "double": ("d", 8), "float64": ("d", 8),
}


# -----------------------------------------------------------------------------
# Public entry points
# -----------------------------------------------------------------------------
def load_scan(file_name: str, data: bytes) -> Dict[str, Any]:
    """Parse an uploaded model into a dict:
        {vertices (N,3), faces (M,3)|None, kind 'mesh'|'points',
         n_vertices, n_faces, bbox (min,max)}.
    Raises ValueError with a readable message on bad input.
    """
    ext = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
    if ext == "obj":
        verts, faces = _parse_obj(data)
    elif ext == "stl":
        verts, faces = _parse_stl(data)
    elif ext == "ply":
        verts, faces = _parse_ply(data)
    elif ext in ("xyz", "pts", "csv", "txt"):
        verts, faces = _parse_points(data), None
    else:
        raise ValueError(
            f"Unsupported file type '.{ext}'. Use one of: "
            f"{', '.join(SUPPORTED_EXT)}."
        )

    if verts is None or len(verts) == 0:
        raise ValueError("No vertices/points found in the file.")
    verts = np.asarray(verts, dtype=float)
    if verts.ndim != 2 or verts.shape[1] != 3:
        raise ValueError("Could not read 3-D coordinates from the file.")

    has_faces = faces is not None and len(faces) > 0
    return {
        "vertices": verts,
        "faces": np.asarray(faces, dtype=int) if has_faces else None,
        "kind": "mesh" if has_faces else "points",
        "n_vertices": int(len(verts)),
        "n_faces": int(len(faces)) if has_faces else 0,
        "bbox": (verts.min(axis=0), verts.max(axis=0)),
    }


def build_scan_figure(scan: Dict[str, Any]) -> go.Figure:
    """True-scale plotly figure: Mesh3d for a mesh, Scatter3d for a point
    cloud (or a large mesh's vertices). `aspectmode='data'` keeps it 1:1."""
    v = scan["vertices"]
    faces = scan["faces"]
    fig = go.Figure()

    if scan["kind"] == "mesh" and faces is not None and len(faces) <= MAX_FACES:
        fig.add_trace(go.Mesh3d(
            x=v[:, 0], y=v[:, 1], z=v[:, 2],
            i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
            intensity=v[:, 2], colorscale="Viridis", showscale=False,
            opacity=1.0, lighting=dict(ambient=0.55, diffuse=0.8),
            hoverinfo="skip", name="As-built scan",
        ))
    else:
        pts = v
        if len(pts) > MAX_POINTS:
            sel = np.random.default_rng(0).choice(
                len(pts), MAX_POINTS, replace=False)
            pts = pts[sel]
        fig.add_trace(go.Scatter3d(
            x=pts[:, 0], y=pts[:, 1], z=pts[:, 2], mode="markers",
            marker=dict(size=1.5, color=pts[:, 2], colorscale="Viridis",
                        showscale=False),
            hoverinfo="skip", name="Point cloud",
        ))

    fig.update_layout(
        scene=dict(
            aspectmode="data",
            xaxis=dict(title="X (m)", color="#5F5E5A", showbackground=False),
            yaxis=dict(title="Y (m)", color="#5F5E5A", showbackground=False),
            zaxis=dict(title="Z (m)", color="#5F5E5A", showbackground=False),
        ),
        height=560,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# -----------------------------------------------------------------------------
# Point clouds (XYZ / PTS / CSV / TXT)
# -----------------------------------------------------------------------------
def _parse_points(data: bytes) -> np.ndarray:
    text = data.decode("utf-8", "replace")
    delim = "," if ("," in text[:2000]) else None
    arr = np.genfromtxt(io.StringIO(text), usecols=(0, 1, 2),
                        comments="#", delimiter=delim, invalid_raise=False)
    if arr.ndim == 1:                       # single row
        arr = arr.reshape(1, -1)
    arr = arr[~np.isnan(arr).any(axis=1)]   # drop header / malformed rows
    return arr


# -----------------------------------------------------------------------------
# OBJ (ASCII)
# -----------------------------------------------------------------------------
def _parse_obj(data: bytes) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    text = data.decode("utf-8", "replace")
    verts, faces = [], []
    for line in text.splitlines():
        if line.startswith("v "):
            p = line.split()
            verts.append([float(p[1]), float(p[2]), float(p[3])])
        elif line.startswith("f "):
            n = len(verts)
            idx = []
            for tok in line.split()[1:]:
                s = tok.split("/")[0]       # f v/vt/vn -> v
                if s:
                    i = int(s)
                    idx.append(i - 1 if i > 0 else n + i)   # 1-based / rel
            for k in range(1, len(idx) - 1):                # fan-triangulate
                faces.append([idx[0], idx[k], idx[k + 1]])
    return (np.asarray(verts, float),
            np.asarray(faces, int) if faces else None)


# -----------------------------------------------------------------------------
# STL (ASCII + binary)
# -----------------------------------------------------------------------------
def _parse_stl(data: bytes) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    if len(data) >= 84:
        ntri = struct.unpack_from("<I", data, 80)[0]
        if len(data) == 84 + ntri * 50:        # exact binary STL size
            return _parse_stl_binary(data, ntri)
    return _parse_stl_ascii(data)


def _parse_stl_binary(data: bytes, ntri: int):
    verts = np.empty((ntri * 3, 3))
    off = 84
    for t in range(ntri):
        vals = struct.unpack_from("<12f", data, off)   # normal + 3 verts
        verts[3 * t] = vals[3:6]
        verts[3 * t + 1] = vals[6:9]
        verts[3 * t + 2] = vals[9:12]
        off += 50                                       # 48 + 2-byte attr
    faces = np.arange(ntri * 3).reshape(ntri, 3)
    return verts, faces


def _parse_stl_ascii(data: bytes):
    text = data.decode("utf-8", "replace")
    verts, cur = [], []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("vertex"):
            p = s.split()
            cur.append([float(p[1]), float(p[2]), float(p[3])])
    verts = np.asarray(cur, float)
    if len(verts) < 3:
        return verts, None
    ntri = len(verts) // 3
    faces = np.arange(ntri * 3).reshape(ntri, 3)
    return verts[:ntri * 3], faces


# -----------------------------------------------------------------------------
# PLY (ASCII + binary little/big-endian)
# -----------------------------------------------------------------------------
def _parse_ply(data: bytes) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    marker = data.find(b"end_header")
    if marker == -1:
        raise ValueError("Not a valid PLY file (no end_header).")
    header_end = data.find(b"\n", marker) + 1
    header = data[:header_end].decode("ascii", "replace")

    fmt = "ascii"
    n_v = n_f = 0
    v_props = []                # (type, name) for vertex element
    cur_elem = None
    for ln in header.splitlines():
        t = ln.split()
        if not t:
            continue
        if t[0] == "format":
            fmt = t[1]
        elif t[0] == "element":
            cur_elem = t[1]
            if t[1] == "vertex":
                n_v = int(t[2])
            elif t[1] == "face":
                n_f = int(t[2])
        elif t[0] == "property" and cur_elem == "vertex":
            v_props.append((t[1], t[-1]))

    names = [p[1] for p in v_props]
    if not all(c in names for c in ("x", "y", "z")):
        raise ValueError("PLY vertex element lacks x/y/z properties.")
    ix, iy, iz = names.index("x"), names.index("y"), names.index("z")
    body = data[header_end:]

    if fmt == "ascii":
        return _parse_ply_ascii(body, n_v, n_f, ix, iy, iz)
    if fmt in ("binary_little_endian", "binary_big_endian"):
        endian = "<" if fmt.endswith("little_endian") else ">"
        return _parse_ply_binary(body, n_v, n_f, v_props, ix, iy, iz, endian)
    raise ValueError(f"Unsupported PLY format '{fmt}'.")


def _parse_ply_ascii(body: bytes, n_v: int, n_f: int, ix, iy, iz):
    lines = body.decode("utf-8", "replace").splitlines()
    verts = np.empty((n_v, 3))
    li = 0
    for i in range(n_v):
        p = lines[li].split()
        li += 1
        verts[i] = (float(p[ix]), float(p[iy]), float(p[iz]))
    faces = []
    for _ in range(n_f):
        if li >= len(lines):
            break
        p = lines[li].split()
        li += 1
        if not p:
            continue
        k = int(p[0])
        idx = [int(x) for x in p[1:1 + k]]
        for m in range(1, k - 1):
            faces.append([idx[0], idx[m], idx[m + 1]])
    return verts, (np.asarray(faces, int) if faces else None)


def _parse_ply_binary(body: bytes, n_v: int, n_f: int, v_props,
                      ix, iy, iz, endian: str):
    rec = endian + "".join(_PLY_T[t][0] for t, _ in v_props)
    size = struct.calcsize(rec)
    verts = np.empty((n_v, 3))
    off = 0
    for i in range(n_v):
        vals = struct.unpack_from(rec, body, off)
        off += size
        verts[i] = (vals[ix], vals[iy], vals[iz])

    # Faces: the common encoding is a list property (uchar count + int
    # indices). Parse defensively; stop if the buffer runs out.
    faces = []
    for _ in range(n_f):
        if off >= len(body):
            break
        k = struct.unpack_from(endian + "B", body, off)[0]
        off += 1
        if k < 3 or off + 4 * k > len(body):
            break
        idx = struct.unpack_from(endian + ("i" * k), body, off)
        off += 4 * k
        for m in range(1, k - 1):
            faces.append([idx[0], idx[m], idx[m + 1]])
    return verts, (np.asarray(faces, int) if faces else None)
