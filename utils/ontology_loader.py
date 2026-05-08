"""
Ontology loading utilities.

Loads the OWL/Turtle ontology exported from Protégé into an rdflib
graph, caches it in Streamlit's session cache, and provides helper
functions to extract defect instances for display.

REVISIONS (Rev 4)
-----------------
1. Namespace migration: tunnel-dt.transurban.com -> w3id.org/tunnel-dt.
2. SPARQL subclass-traversal fix. Defects are typed as subclasses of
   DefectCondition (e.g. tun:LeakingJoints, tun:Spalls). rdflib's
   SPARQL engine does NOT traverse rdfs:subClassOf without OWL
   reasoning, so the previous query missed every TTL-defined instance.
   The new query uses property-path syntax `rdf:type/rdfs:subClassOf*`
   so subclass-typed defects are found.
3. JSON-to-graph materialisation. After loading defects from the JSON
   fallback (data/defects_tunnel_a.json), the loader now writes them
   back into the graph as triples — so SPARQL Console queries can
   reach every defect, regardless of whether it came from the TTL or
   the JSON.
"""

import json
from pathlib import Path
from typing import List, Dict, Any

import streamlit as st
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDF, RDFS, OWL, XSD

# -----------------------------------------------------------------------------
# Namespaces — match the URIs used in your Protégé ontology
# -----------------------------------------------------------------------------
TUN = Namespace("http://w3id.org/tunnel-dt/ontology/v1.2#")
COBIE = Namespace("http://w3id.org/tunnel-dt/cobie#")
RADS = Namespace("http://w3id.org/tunnel-dt/rads#")

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

    After loading the TTL files, also materialises any defects in
    data/defects_tunnel_a.json into the graph as triples, so SPARQL
    queries on Page 3 can reach every defect.
    """
    g = Graph()
    g.bind("tun", TUN)
    g.bind("cobie", COBIE)
    g.bind("rads", RADS)

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

    # Materialise JSON-defined defects into the graph as triples.
    # Catches the case where the TTL only has 2 demo instances but the
    # JSON has the full 7 — we want all 7 reachable via SPARQL.
    _materialise_json_defects_into_graph(g)

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

    # Mark defect-type subclasses for proper hierarchy traversal
    for sub in ["Cracks", "Spalls", "LeakingJoints", "Delaminations"]:
        g.add((TUN[sub], RDFS.subClassOf, TUN.DefectCondition))

    properties = [
        "hasDefect", "hasMechanism", "hasIndicator", "hasCause",
        "hasIntervention", "detectedBy", "atFMEALevel", "atChainage",
        "atRingID", "atPosition", "hasType", "hasSeverity", "hasPriority",
        "estimatedCost", "completenessScore", "hasDescription",
    ]
    for p in properties:
        g.add((TUN[p], RDF.type, OWL.ObjectProperty))


def _materialise_json_defects_into_graph(g: Graph) -> None:
    """
    Read data/defects_tunnel_a.json and add each defect as triples in
    the graph, so SPARQL Console queries can find them regardless of
    whether they were originally in the TTL.

    Skips a defect if a triple `tun:<id> rdf:type ?` already exists,
    so TTL-defined instances are not double-counted.
    """
    sample_path = DATA_DIR / "defects_tunnel_a.json"
    if not sample_path.exists():
        return

    try:
        with open(sample_path) as f:
            defects = json.load(f)
    except Exception:
        return

    type_to_class = {
        "Cracks": TUN.Cracks,
        "Spalls": TUN.Spalls,
        "LeakingJoints": TUN.LeakingJoints,
        "Delamination": TUN.Delaminations,
        "Delaminations": TUN.Delaminations,
        "Efflorescence": TUN.Efflorescence,
        "RebarCorrosion": TUN.RebarCorrosion,
    }

    for d in defects:
        defect_id = d.get("defect_id")
        if not defect_id:
            continue

        subj = TUN[defect_id]

        # Skip if already in graph (TTL took precedence)
        if (subj, RDF.type, None) in g:
            continue

        defect_type = d.get("defect_type", "")
        cls = type_to_class.get(defect_type, TUN.DefectCondition)
        g.add((subj, RDF.type, cls))
        g.add((subj, RDF.type, OWL.NamedIndividual))

        # Ensure the subclass relationship exists for the rdfs:subClassOf*
        # property path to traverse correctly
        g.add((cls, RDFS.subClassOf, TUN.DefectCondition))

        if defect_type:
            g.add((subj, TUN.hasType, Literal(defect_type)))
        if d.get("ring_id") is not None:
            try:
                g.add((subj, TUN.atRingID,
                       Literal(int(d["ring_id"]), datatype=XSD.integer)))
            except (ValueError, TypeError):
                g.add((subj, TUN.atRingID, Literal(str(d["ring_id"]))))
        if d.get("chainage_m") is not None:
            g.add((subj, TUN.atChainage,
                   Literal(float(d["chainage_m"]), datatype=XSD.decimal)))
        if d.get("position"):
            g.add((subj, TUN.atPosition, Literal(d["position"])))
        if d.get("severity"):
            g.add((subj, TUN.hasSeverity, Literal(d["severity"])))
        if d.get("priority"):
            g.add((subj, TUN.hasPriority, Literal(d["priority"])))
        if d.get("estimated_cost_aud"):
            g.add((subj, TUN.estimatedCost,
                   Literal(float(d["estimated_cost_aud"]),
                           datatype=XSD.decimal)))
        if d.get("completeness_score") is not None:
            g.add((subj, TUN.completenessScore,
                   Literal(float(d["completeness_score"]),
                           datatype=XSD.decimal)))
        if d.get("description"):
            g.add((subj, TUN.hasDescription, Literal(d["description"])))

        # Modalities used (if recorded in JSON)
        for mod in d.get("modality_evidence", {}).keys():
            mod_uri = TUN[mod]
            g.add((subj, TUN.detectedBy, mod_uri))


@st.cache_data(show_spinner=False)
def load_defects(_graph: Graph) -> List[Dict[str, Any]]:
    """
    Extract defect instances for display.

    Tries SPARQL first (now with subclass traversal so subclass-typed
    instances are found). If the SPARQL query yields fewer instances
    than the JSON file, falls back to / merges with the JSON.
    """
    # Use a property path so subclass-typed defects are matched.
    # Without `rdfs:subClassOf*`, an instance typed as `tun:LeakingJoints`
    # is not matched by `?d rdf:type tun:DefectCondition` — that was the
    # core bug. The path matches direct types AND subclass-typed instances.
    query = """
    PREFIX tun: <http://w3id.org/tunnel-dt/ontology/v1.2#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?defect ?type ?ring ?chainage ?position
           ?severity ?priority ?cost ?completeness ?description
    WHERE {
        ?defect rdf:type/rdfs:subClassOf* tun:DefectCondition .
        OPTIONAL { ?defect tun:hasType ?type . }
        OPTIONAL { ?defect tun:atRingID ?ring . }
        OPTIONAL { ?defect tun:atChainage ?chainage . }
        OPTIONAL { ?defect tun:atPosition ?position . }
        OPTIONAL { ?defect tun:hasSeverity ?severity . }
        OPTIONAL { ?defect tun:hasPriority ?priority . }
        OPTIONAL { ?defect tun:estimatedCost ?cost . }
        OPTIONAL { ?defect tun:completenessScore ?completeness . }
        OPTIONAL { ?defect tun:hasDescription ?description . }
    }
    """

    try:
        results = list(_graph.query(query))
    except Exception:
        results = []

    sparql_defects = []
    seen_ids = set()
    if results:
        for row in results:
            defect_id = str(row[0]).split("#")[-1]
            if defect_id in seen_ids:
                continue
            seen_ids.add(defect_id)
            sparql_defects.append({
                "defect_id": defect_id,
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

    # Always load the JSON to enrich/augment with fields that aren't
    # easily expressed as triples (modality_evidence, fmea_chain,
    # prescribed_interventions, ...).
    sample_path = DATA_DIR / "defects_tunnel_a.json"
    json_defects = []
    if sample_path.exists():
        try:
            with open(sample_path) as f:
                json_defects = json.load(f)
        except Exception:
            json_defects = []

    # Merge: prefer JSON dict (richer fields) when IDs match;
    # include SPARQL-only IDs that aren't in the JSON.
    json_by_id = {d.get("defect_id"): d for d in json_defects
                  if d.get("defect_id")}

    merged = []
    used_ids = set()

    # Start from JSON (richer payload) for any defect that exists there
    for d in json_defects:
        merged.append(d)
        used_ids.add(d.get("defect_id"))

    # Add any SPARQL-only defects (TTL-defined but not in JSON)
    for d in sparql_defects:
        if d["defect_id"] not in used_ids:
            merged.append(d)
            used_ids.add(d["defect_id"])

    return merged


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
    PREFIX tun: <http://w3id.org/tunnel-dt/ontology/v1.2#>

    SELECT ?component ?mechanism ?defectType ?indicator ?indValue ?cause
           ?threshold ?intervention ?sourceRef
    WHERE {{
        OPTIONAL {{ tun:{defect_id} tun:atComponent ?component . }}
        OPTIONAL {{ tun:{defect_id} tun:hasMechanism ?mechanism . }}
        OPTIONAL {{ tun:{defect_id} tun:hasType ?defectType . }}
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
