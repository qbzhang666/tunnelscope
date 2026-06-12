"""
IFC export — defects and tunnel lining as Industry Foundation Classes
=====================================================================

Writes a valid IFC4 SPF (STEP) file from the digital twin's data, so
the model opens in any openBIM viewer (BIMvision, Solibri, BlenderBIM,
usBIM...). Pure Python — no ifcopenshell dependency.

Mapping (the ontology ↔ IFC bridge):

  Tunnel               → IfcBuilding with ObjectType='Tunnel'.
                         (IfcTunnel is only standardised in the
                         upcoming IFC 4.4; IfcBuilding keeps the file
                         openable in today's viewers. Swap when 4.4
                         lands.)
  Lining               → IfcBuildingElementProxy with an
                         IfcCircleHollowProfileDef swept the tunnel
                         length — radius and wall thickness from the
                         BIM as-built record.
  Defect record        → IfcBuildingElementProxy (small cube) placed
                         at its chainage along the axis and its
                         cross-section angle on the lining.
  Defect attributes    → Pset_TunnelDT_Defect property set: defect
                         type, ring, chainage, position, priority,
                         severity, estimated cost, completeness,
                         status, discovery date.
  Defect type          → IfcClassificationReference whose Location is
                         the ontology class URI (e.g.
                         http://w3id.org/tunnel-dt/ontology/v1.2#Cracks),
                         attached via IfcRelAssociatesClassification.
                         The IFC file and the knowledge base therefore
                         point at the SAME identifier for a defect
                         type — that is the semantic link.

IFC requires ASCII in SPF strings and decimal points in REALs; both
are handled by the small helpers below.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils.bim3d import position_to_angle_deg, DEFAULT_DIAMETER_M

ONTOLOGY_BASE = "http://w3id.org/tunnel-dt/ontology/v1.2"

# IFC GlobalId base-64 alphabet (not standard base64)
_GUID_CHARS = ("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               "abcdefghijklmnopqrstuvwxyz_$")


def _new_guid() -> str:
    """22-character IFC GlobalId from a random UUID."""
    n = uuid.uuid4().int
    chars = []
    for _ in range(22):
        n, rem = divmod(n, 64)
        chars.append(_GUID_CHARS[rem])
    return "".join(reversed(chars))


def _s(text: Any) -> str:
    """Escape a python value as an SPF string literal."""
    t = str(text if text is not None else "")
    t = t.encode("ascii", "replace").decode("ascii")
    t = t.replace("\\", "\\\\").replace("'", "''")
    return f"'{t}'"


def _f(value: Any) -> str:
    """SPF REAL — always carries a decimal point."""
    return f"{float(value):.4f}"


class _IfcWriter:
    """Tiny incremental SPF writer: add(entity) returns its #id."""

    def __init__(self) -> None:
        self.lines: List[str] = []

    def add(self, entity: str) -> str:
        ref = f"#{len(self.lines) + 1}"
        self.lines.append(f"{ref}={entity};")
        return ref


def build_ifc(
    tunnel: Dict[str, Any],
    bim_tunnel: Optional[Dict[str, Any]],
    defects: List[Dict[str, Any]],
) -> str:
    """Assemble the IFC4 file text for one tunnel and its defects."""
    w = _IfcWriter()
    ts = int(datetime.now(timezone.utc).timestamp())
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    length = float(tunnel.get("length_m", 1000))
    diameter = float((bim_tunnel or {}).get("internal_diameter_m")
                     or DEFAULT_DIAMETER_M)
    r_inner = diameter / 2.0
    lining_t = float((bim_tunnel or {}).get("lining_thickness_m") or 0.4)

    # ---- ownership / units / context ------------------------------------
    person = w.add("IFCPERSON($,$,'TunnelDT',$,$,$,$,$)")
    org = w.add("IFCORGANIZATION($,'Tunnel DT Dashboard',$,$,$)")
    pno = w.add(f"IFCPERSONANDORGANIZATION({person},{org},$)")
    app = w.add(f"IFCAPPLICATION({org},'1.0','Tunnel DT Dashboard','TunnelDT')")
    owner = w.add(f"IFCOWNERHISTORY({pno},{app},$,.ADDED.,$,$,$,{ts})")

    u_len = w.add("IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)")
    u_area = w.add("IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.)")
    u_vol = w.add("IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.)")
    u_ang = w.add("IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.)")
    units = w.add(f"IFCUNITASSIGNMENT(({u_len},{u_area},{u_vol},{u_ang}))")

    origin = w.add("IFCCARTESIANPOINT((0.,0.,0.))")
    axis_z = w.add("IFCDIRECTION((0.,0.,1.))")
    axis_x = w.add("IFCDIRECTION((1.,0.,0.))")
    wcs = w.add(f"IFCAXIS2PLACEMENT3D({origin},{axis_z},{axis_x})")
    ctx = w.add(
        f"IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.E-5,{wcs},$)"
    )

    # ---- spatial structure: project > site > building(=tunnel) ----------
    project = w.add(
        f"IFCPROJECT({_s(_new_guid())},{owner},{_s('Tunnel DT')},"
        f"{_s('Serviceability-oriented tunnel maintenance digital twin')},"
        f"$,$,$,({ctx}),{units})"
    )
    site_plc = w.add(f"IFCLOCALPLACEMENT($,{wcs})")
    site = w.add(
        f"IFCSITE({_s(_new_guid())},{owner},{_s('Site')},$,$,{site_plc},"
        f"$,$,.ELEMENT.,$,$,$,$,$)"
    )
    bld_plc = w.add(f"IFCLOCALPLACEMENT({site_plc},{wcs})")
    building = w.add(
        f"IFCBUILDING({_s(_new_guid())},{owner},{_s(tunnel.get('label', 'Tunnel'))},"
        f"{_s('Road tunnel (IfcTunnel arrives in IFC 4.4)')},{_s('Tunnel')},"
        f"{bld_plc},$,{_s(tunnel.get('tunnel_id', ''))},.ELEMENT.,$,$,$)"
    )
    w.add(
        f"IFCRELAGGREGATES({_s(_new_guid())},{owner},$,$,{project},({site}))"
    )
    w.add(
        f"IFCRELAGGREGATES({_s(_new_guid())},{owner},$,$,{site},({building}))"
    )

    contained: List[str] = []

    # ---- lining: hollow circular profile swept the tunnel length --------
    prof_plc2d = w.add(
        f"IFCAXIS2PLACEMENT2D({w.add('IFCCARTESIANPOINT((0.,0.))')},$)"
    )
    profile = w.add(
        f"IFCCIRCLEHOLLOWPROFILEDEF(.AREA.,{_s('Lining')},{prof_plc2d},"
        f"{_f(r_inner + lining_t)},{_f(lining_t)})"
    )
    # Extrusion local z is rotated onto global +x (the chainage axis)
    sweep_plc = w.add(
        f"IFCAXIS2PLACEMENT3D({origin},{axis_x},"
        f"{w.add('IFCDIRECTION((0.,1.,0.))')})"
    )
    solid = w.add(
        f"IFCEXTRUDEDAREASOLID({profile},{sweep_plc},{axis_z},{_f(length)})"
    )
    lining_shape = w.add(
        f"IFCPRODUCTDEFINITIONSHAPE($,$,({w.add(f'IFCSHAPEREPRESENTATION({ctx},' + _s('Body') + ',' + _s('SweptSolid') + f',({solid}))')}))"
    )
    lining_plc = w.add(f"IFCLOCALPLACEMENT({bld_plc},{wcs})")
    lining = w.add(
        f"IFCBUILDINGELEMENTPROXY({_s(_new_guid())},{owner},"
        f"{_s('Tunnel lining')},"
        f"{_s(f'O {diameter} m, lining {lining_t} m, from BIM as-built' if bim_tunnel else 'Generic lining (no BIM record)')},"
        f"$,{lining_plc},{lining_shape},$,$)"
    )
    contained.append(lining)

    # ---- defects: cubes at (chainage, cross-section angle) --------------
    cube = 0.6  # marker edge, metres
    half = cube / 2.0
    cube_profile = w.add(
        f"IFCRECTANGLEPROFILEDEF(.AREA.,{_s('DefectMarker')},"
        f"{prof_plc2d},{_f(cube)},{_f(cube)})"
    )

    defect_elements: List[str] = []
    by_type: Dict[str, List[str]] = {}

    for d in defects:
        chainage = float(d.get("chainage_m") or 0)
        if chainage <= 0:
            continue
        chainage = min(chainage, length)
        angle = math.radians(position_to_angle_deg(d.get("position", "")))
        y = r_inner * math.sin(angle)
        z = r_inner * math.cos(angle)

        d_origin = w.add(
            f"IFCCARTESIANPOINT(({_f(chainage - half)},{_f(y - half)},"
            f"{_f(z - half)}))"
        )
        d_plc3d = w.add(f"IFCAXIS2PLACEMENT3D({d_origin},{axis_z},{axis_x})")
        d_plc = w.add(f"IFCLOCALPLACEMENT({bld_plc},{d_plc3d})")
        d_solid = w.add(
            f"IFCEXTRUDEDAREASOLID({cube_profile},"
            f"{w.add(f'IFCAXIS2PLACEMENT3D({origin},$,$)')},{axis_z},{_f(cube)})"
        )
        d_shape = w.add(
            f"IFCPRODUCTDEFINITIONSHAPE($,$,({w.add(f'IFCSHAPEREPRESENTATION({ctx},' + _s('Body') + ',' + _s('SweptSolid') + f',({d_solid}))')}))"
        )
        elem = w.add(
            f"IFCBUILDINGELEMENTPROXY({_s(_new_guid())},{owner},"
            f"{_s(d.get('defect_id', 'Defect'))},"
            f"{_s(d.get('description', ''))},"
            f"{_s(d.get('defect_type', ''))},{d_plc},{d_shape},"
            f"{_s(d.get('defect_id', ''))},$)"
        )
        contained.append(elem)
        defect_elements.append(elem)
        by_type.setdefault(d.get("defect_type") or "Unclassified",
                           []).append(elem)

        # Property set with the defect's record
        props = []
        prop_values = [
            ("DefectType", "IFCLABEL", _s(d.get("defect_type", ""))),
            ("RingID", "IFCLABEL", _s(d.get("ring_id", ""))),
            ("Chainage_m", "IFCREAL", _f(chainage)),
            ("Position", "IFCLABEL", _s(d.get("position", ""))),
            ("Priority", "IFCLABEL", _s(d.get("priority", ""))),
            ("Severity", "IFCLABEL", _s(d.get("severity", ""))),
            ("EstimatedCost_AUD", "IFCREAL",
             _f(d.get("estimated_cost_aud") or 0)),
            ("CompletenessScore", "IFCREAL",
             _f(d.get("completeness_score") or 0)),
            ("Status", "IFCLABEL", _s(d.get("status", ""))),
            ("DiscoveredOn", "IFCLABEL", _s(d.get("discovered_on", ""))),
        ]
        for name, ifc_type, value in prop_values:
            props.append(w.add(
                f"IFCPROPERTYSINGLEVALUE({_s(name)},$,{ifc_type}({value}),$)"
            ))
        pset = w.add(
            f"IFCPROPERTYSET({_s(_new_guid())},{owner},"
            f"{_s('Pset_TunnelDT_Defect')},$,({','.join(props)}))"
        )
        w.add(
            f"IFCRELDEFINESBYPROPERTIES({_s(_new_guid())},{owner},$,$,"
            f"({elem}),{pset})"
        )

    # ---- classification: defect types -> ontology class URIs ------------
    classification = w.add(
        f"IFCCLASSIFICATION({_s('w3id.org/tunnel-dt')},{_s('1.2')},$,"
        f"{_s('Tunnel-DT Maintenance Ontology')},"
        f"{_s('OWL ontology behind the Tunnel DT digital twin')},"
        f"{_s(ONTOLOGY_BASE)},$)"
    )
    for defect_type, elems in sorted(by_type.items()):
        ref = w.add(
            f"IFCCLASSIFICATIONREFERENCE("
            f"{_s(f'{ONTOLOGY_BASE}#{defect_type}')},"
            f"{_s(defect_type)},{_s(defect_type)},{classification},$,$)"
        )
        w.add(
            f"IFCRELASSOCIATESCLASSIFICATION({_s(_new_guid())},{owner},"
            f"{_s('Defect taxonomy')},$,({','.join(elems)}),{ref})"
        )

    # ---- containment ------------------------------------------------------
    w.add(
        f"IFCRELCONTAINEDINSPATIALSTRUCTURE({_s(_new_guid())},{owner},"
        f"$,$,({','.join(contained)}),{building})"
    )

    # ---- assemble the file -------------------------------------------------
    header = (
        "ISO-10303-21;\n"
        "HEADER;\n"
        "FILE_DESCRIPTION(('Tunnel DT defect model'),'2;1');\n"
        f"FILE_NAME({_s(tunnel.get('tunnel_id', 'tunnel') + '_defects.ifc')},"
        f"{_s(now_iso)},('Tunnel DT'),('Tunnel DT Dashboard'),"
        "'TunnelDT 1.0','TunnelDT 1.0','');\n"
        "FILE_SCHEMA(('IFC4'));\n"
        "ENDSEC;\n"
        "DATA;\n"
    )
    footer = "ENDSEC;\nEND-ISO-10303-21;\n"
    return header + "\n".join(w.lines) + "\n" + footer
