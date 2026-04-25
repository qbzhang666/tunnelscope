"""
Pre-built SPARQL queries for common dashboard operations.

Each query is a function returning the query string, so namespaces can
be substituted if your ontology uses different URIs. The raw .rq files
in queries/ mirror these for reference and reuse in other tools.
"""

from pathlib import Path

QUERIES_DIR = Path(__file__).parent.parent / "queries"


PREFIX_BLOCK = """
PREFIX tun:  <http://tunnel-dt.transurban.com/ontology/v1.2#>
PREFIX cobie: <http://tunnel-dt.transurban.com/cobie#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
"""


def query_all_defects_by_ring(ring_id: int) -> str:
    return PREFIX_BLOCK + f"""
    SELECT ?defect ?type ?mechanism ?severity ?priority
    WHERE {{
        ?defect rdf:type tun:DefectCondition ;
                tun:atRingID {ring_id} ;
                tun:hasType ?type ;
                tun:hasMechanism ?mechanism .
        OPTIONAL {{ ?defect tun:hasSeverity ?severity . }}
        OPTIONAL {{ ?defect tun:hasPriority ?priority . }}
    }}
    ORDER BY DESC(?priority)
    """


def query_completeness_score(defect_id: str) -> str:
    return PREFIX_BLOCK + f"""
    SELECT (COUNT(DISTINCT ?level) AS ?levelsCovered)
           (COUNT(DISTINCT ?reqLevel) AS ?levelsRequired)
    WHERE {{
        tun:{defect_id} tun:requiresFMEALevel ?reqLevel .
        OPTIONAL {{
            tun:{defect_id} tun:hasEvidenceAtLevel ?level .
            FILTER(?level = ?reqLevel)
        }}
    }}
    """


def query_high_priority_defects() -> str:
    return PREFIX_BLOCK + """
    SELECT ?defect ?ring ?chainage ?type ?priority ?cost
    WHERE {
        ?defect rdf:type tun:DefectCondition ;
                tun:hasPriority "HIGH" ;
                tun:atRingID ?ring ;
                tun:atChainage ?chainage ;
                tun:hasType ?type .
        OPTIONAL { ?defect tun:estimatedCost ?cost . }
    }
    ORDER BY ?chainage
    """


def query_fmea_chain_for_defect(defect_id: str) -> str:
    return PREFIX_BLOCK + f"""
    SELECT ?component ?mechanism ?indicator ?indValue
           ?cause ?intervention ?sourceRef
    WHERE {{
        tun:{defect_id} tun:atComponent ?component ;
                        tun:hasMechanism ?mechanism .
        OPTIONAL {{
            tun:{defect_id} tun:hasIndicator ?indicator .
            ?indicator tun:indicatorValue ?indValue .
        }}
        OPTIONAL {{ tun:{defect_id} tun:hasPotentialCause ?cause . }}
        OPTIONAL {{
            tun:{defect_id} tun:hasIntervention ?intervention .
            ?intervention tun:sourceReference ?sourceRef .
        }}
    }}
    """


def query_modality_coverage_stats() -> str:
    return PREFIX_BLOCK + """
    SELECT ?modality (COUNT(?defect) AS ?defectCount)
    WHERE {
        ?defect rdf:type tun:DefectCondition ;
                tun:detectedBy ?modality .
    }
    GROUP BY ?modality
    ORDER BY DESC(?defectCount)
    """


def query_defects_missing_cause_level() -> str:
    """Find defects with incomplete FMEA — missing cause-level evidence."""
    return PREFIX_BLOCK + """
    SELECT ?defect ?ring ?chainage ?type
    WHERE {
        ?defect rdf:type tun:DefectCondition ;
                tun:atRingID ?ring ;
                tun:atChainage ?chainage ;
                tun:hasType ?type .
        FILTER NOT EXISTS {
            ?defect tun:hasPotentialCause ?c .
        }
    }
    """


def query_interventions_per_standard() -> str:
    """Count prescribed interventions grouped by standard reference."""
    return PREFIX_BLOCK + """
    SELECT ?standard (COUNT(?intervention) AS ?count)
    WHERE {
        ?intervention rdf:type tun:Intervention ;
                      tun:sourceReference ?standard .
    }
    GROUP BY ?standard
    ORDER BY DESC(?count)
    """


def load_query_from_file(filename: str) -> str:
    """Load a .rq query file from the queries/ directory."""
    path = QUERIES_DIR / filename
    if path.exists():
        return path.read_text()
    return ""


# -----------------------------------------------------------------------------
# Example queries for the SPARQL console dropdown
# -----------------------------------------------------------------------------
EXAMPLE_QUERIES = {
    "All defects at Ring 1247": query_all_defects_by_ring(1247),
    "High priority defects": query_high_priority_defects(),
    "FMEA chain for D-1247-L": query_fmea_chain_for_defect("D-1247-L"),
    "Modality coverage stats": query_modality_coverage_stats(),
    "Defects missing cause-level evidence": query_defects_missing_cause_level(),
    "Interventions per standard": query_interventions_per_standard(),
}
