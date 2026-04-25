"""
Ontology loading utilities.

Loads the OWL/Turtle ontology exported from Protégé into an rdflib
graph, caches it in Streamlit's session cache, and provides helper
functions to extract defect instances for display.

If the Turtle file is missing, falls back to the JSON sample data in
data/defects_tunnel_a.json so the app still runs.
"""

import json
from pathlib import Path
from typing import List, Dict, Any

import streamlit as st
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL

# -----------------------------------------------------------------------------
# Namespaces — match the URIs used in your Protégé ontology
# -----------------------------------------------------------------------------
TUN = Namespace("http://tunnel-dt.transurban.com/ontology/v1.2#")
COBIE = Namespace("http://tunnel-dt.transurban.com/cobie#")

# Paths
ROOT = Path(__file__).parent.parent
ONTOLOGY_DIR = ROOT / "ontology"
DATA_DIR = ROOT / "data"

ONTOLOGY_FILES = [
    "tunnel_maintenance.ttl",
    "cobie_ontology.ttl",
    "austroads_rads.ttl",
]


# -----------------------------------------------------------------------------
# Loaders
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def load_ontology() -> Graph:
    """
    Load all Turtle files in the ontology/ directory into a single
    rdflib Graph. Cached for the session.
    """
    g = Graph()
    g.bind("tun", TUN)
    g.bind("cobie", COBIE)

    loaded = 0
    for fname in ONTOLOGY_FILES:
        fpath = ONTOLOGY_DIR / fname
        if fpath.exists():
            try:
                g.parse(str(fpath), format="turtle")
                loaded += 1
            except Exception as e:
                st.warning(f"Could not parse {fname}: {e}")

    if loaded == 0:
        # Fallback — no ontology files found, create minimal schema in-memory
        _create_minimal_schema(g)

    return g


def _create_minimal_schema(g: Graph) -> None:
    """Create a minimal in-memory ontology so the app still runs."""
    classes = [
        "DefectCondition", "FailureMechanism", "MeasuredIndicator",
        "PotentialCause", "Intervention", "Component", "SensingModality",
        "Cracks", "Spalls", "LeakingJoints", "Delaminations",
        "RGB", "RGBD", "Thermal", "GPR",
    ]
    for c in classes:
        g.add((TUN[c], RDF.type, OWL.Class))

    properties = [
        "hasDefect", "hasMechanism", "hasIndicator", "hasCause",
        "hasIntervention", "detectedBy", "atFMEALevel", "atChainage",
        "atRingID",
    ]
    for p in properties:
        g.add((TUN[p], RDF.type, OWL.ObjectProperty))


@st.cache_data(show_spinner=False)
def load_defects(_graph: Graph) -> List[Dict[str, Any]]:
    """
    Extract defect instances for display. Tries SPARQL first; if no
    instances exist in the ontology, falls back to JSON sample data.
    """
    # Try SPARQL query first
    query = """
    PREFIX tun: <http://tunnel-dt.transurban.com/ontology/v1.2#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

    SELECT ?defect ?type ?ring ?chainage ?position
           ?severity ?priority ?cost ?completeness ?description
    WHERE {
        ?defect rdf:type tun:DefectCondition ;
                tun:hasType ?type ;
                tun:atRingID ?ring ;
                tun:atChainage ?chainage ;
                tun:atPosition ?position .
        OPTIONAL { ?defect tun:hasSeverity ?severity . }
        OPTIONAL { ?defect tun:hasPriority ?priority . }
        OPTIONAL { ?defect tun:estimatedCost ?cost . }
        OPTIONAL { ?defect tun:completenessScore ?completeness . }
        OPTIONAL { ?defect tun:hasDescription ?description . }
    }
    """

    results = list(_graph.query(query))

    if results:
        defects = []
        for row in results:
            defects.append({
                "defect_id": str(row[0]).split("#")[-1],
                "defect_type": str(row[1]) if row[1] else "",
                "ring_id": int(row[2]) if row[2] else 0,
                "chainage_m": float(row[3]) if row[3] else 0.0,
                "position": str(row[4]) if row[4] else "",
                "severity": str(row[5]) if row[5] else "",
                "priority": str(row[6]) if row[6] else "MEDIUM",
                "estimated_cost_aud": float(row[7]) if row[7] else 0,
                "completeness_score": float(row[8]) if row[8] else 0.5,
                "description": str(row[9]) if row[9] else "",
                "status": "Active",
            })
        return defects

    # Fallback — load sample JSON
    sample_path = DATA_DIR / "defects_tunnel_a.json"
    if sample_path.exists():
        with open(sample_path) as f:
            return json.load(f)

    return []


# -----------------------------------------------------------------------------
# Defect detail extraction
# -----------------------------------------------------------------------------
def get_defect_by_id(graph: Graph, defect_id: str) -> Dict[str, Any]:
    """Return a single defect's full record with FMEA chain data."""
    defects = load_defects(graph)
    for d in defects:
        if d.get("defect_id") == defect_id:
            return d
    return {}


def get_fmea_chain(graph: Graph, defect_id: str) -> List[Dict[str, Any]]:
    """
    Traverse the FMEA reasoning chain for a defect:
    Component → Mechanism → Defect → Indicator → Cause → Threshold → Intervention
    """
    query = f"""
    PREFIX tun: <http://tunnel-dt.transurban.com/ontology/v1.2#>

    SELECT ?component ?mechanism ?defectType ?indicator ?indValue ?cause
           ?threshold ?intervention ?sourceRef
    WHERE {{
        tun:{defect_id} tun:atComponent ?component ;
                        tun:hasMechanism ?mechanism ;
                        tun:hasType ?defectType .
        OPTIONAL {{
            tun:{defect_id} tun:hasIndicator ?indicator .
            ?indicator tun:indicatorValue ?indValue .
        }}
        OPTIONAL {{ tun:{defect_id} tun:hasPotentialCause ?cause . }}
        OPTIONAL {{ tun:{defect_id} tun:triggersThreshold ?threshold . }}
        OPTIONAL {{
            tun:{defect_id} tun:hasIntervention ?intervention .
            ?intervention tun:sourceReference ?sourceRef .
        }}
    }}
    """

    try:
        results = list(graph.query(query))
    except Exception:
        results = []

    chain = []
    if results:
        for row in results:
            chain.append({
                "component": str(row[0]).split("#")[-1] if row[0] else "",
                "mechanism": str(row[1]).split("#")[-1] if row[1] else "",
                "defect_type": str(row[2]).split("#")[-1] if row[2] else "",
                "indicator": str(row[3]).split("#")[-1] if row[3] else "",
                "indicator_value": str(row[4]) if row[4] else "",
                "cause": str(row[5]).split("#")[-1] if row[5] else "",
                "threshold": str(row[6]).split("#")[-1] if row[6] else "",
                "intervention": str(row[7]).split("#")[-1] if row[7] else "",
                "source_reference": str(row[8]) if row[8] else "",
            })

    return chain


def get_modality_evidence(graph: Graph, defect_id: str) -> Dict[str, Dict]:
    """
    Return evidence from each modality for a specific defect.

    Returns dict keyed by modality (RGB, RGBD, Thermal, GPR) with
    observation value, confidence, and FMEA chain level.
    """
    defect = get_defect_by_id(graph, defect_id)
    return defect.get("modality_evidence", {})
