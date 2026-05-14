"""
Verification script for Rev 11 OWL 2 RL reasoner activation.

Run this AFTER deploying the Rev 11 patch to confirm the reasoner is
actually expanding the graph at load time. The script:

  1. Loads the ontology via the patched loader
  2. Counts triples before and after a deliberate roundtrip
  3. Probes a known subclass relationship that owlrl should materialise
  4. Reports the verdict

Usage (from the repo root, with the streamlit virtualenv active):

    python verify_owlrl.py

Expected output on a healthy patch:

    OWL 2 RL reasoner: ACTIVE
    Graph triple count after closure: <N>
    Subclass inference test: PASS
    (D-1247-L is correctly inferred as a DefectCondition via Spalls subclass)

Expected output if the patch is incomplete or owlrl is missing:

    OWL 2 RL reasoner: INACTIVE
    Subclass inference test: FAIL
    Falling back to SPARQL property paths (still works for queries,
    but the OWL 2 RL claim in the paper is not literally true).
"""

import sys
from pathlib import Path

# Allow importing from utils/ when run from repo root
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

try:
    import owlrl
    OWLRL_INSTALLED = True
except ImportError:
    OWLRL_INSTALLED = False

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS

# Mirror the loader's namespace
TUN_NS = "http://w3id.org/tunnel-dt/ontology/v1.2#"


def main() -> int:
    # Streamlit is needed because the loader imports st.warning etc.
    # We stub it with a minimal mock so the test runs standalone.
    import types
    streamlit_mock = types.ModuleType("streamlit")
    streamlit_mock.warning = lambda *a, **kw: None
    streamlit_mock.cache_resource = lambda **kw: (lambda f: f)
    streamlit_mock.cache_data = lambda **kw: (lambda f: f)
    sys.modules["streamlit"] = streamlit_mock

    from utils.ontology_loader import load_ontology

    print("=" * 60)
    print("Rev 11 OWL 2 RL Reasoner Verification")
    print("=" * 60)
    print()

    if not OWLRL_INSTALLED:
        print("OWL 2 RL reasoner: INACTIVE (owlrl package not installed)")
        print("Action: `pip install owlrl` and re-run.")
        return 1

    print("owlrl package: installed")
    print("Loading ontology...")
    g = load_ontology()

    # Count triples
    triple_count = len(g)
    print(f"Graph triple count after closure: {triple_count:,}")

    # Probe a subclass inference. If owlrl ran, any defect typed as
    # tun:Spalls should also be reachable as tun:DefectCondition via
    # rdf:type directly (no property path needed).
    spalls = URIRef(f"{TUN_NS}Spalls")
    defect_condition = URIRef(f"{TUN_NS}DefectCondition")

    # Find all instances directly typed as DefectCondition (post-closure)
    direct_match_query = """
        PREFIX tun: <http://w3id.org/tunnel-dt/ontology/v1.2#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?d WHERE { ?d rdf:type tun:DefectCondition . }
    """
    direct_results = list(g.query(direct_match_query))

    # Find all instances reached via subclass property path (works always)
    path_match_query = """
        PREFIX tun: <http://w3id.org/tunnel-dt/ontology/v1.2#>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?d WHERE { ?d rdf:type/rdfs:subClassOf* tun:DefectCondition . }
    """
    path_results = list(g.query(path_match_query))

    print()
    print(f"Defects via direct rdf:type DefectCondition:    {len(direct_results)}")
    print(f"Defects via rdf:type/rdfs:subClassOf*:          {len(path_results)}")

    if len(direct_results) == len(path_results) and len(direct_results) > 0:
        print()
        print("Subclass inference test: PASS")
        print("OWL 2 RL reasoner is ACTIVE — the closure has been materialised")
        print("and direct rdf:type queries reach every defect.")
        return 0
    elif len(path_results) > len(direct_results):
        print()
        print("Subclass inference test: FAIL")
        print("Property-path queries return more results than direct queries,")
        print("which means subclass inferences are NOT being materialised.")
        print()
        print("Possible causes:")
        print("  - owlrl is installed but not invoked from load_ontology()")
        print("  - The DeductiveClosure call is wrapped in a try/except that's")
        print("    silently swallowing an error")
        print("  - Streamlit's cache_resource is returning a stale un-expanded")
        print("    graph from a previous session — restart the app and retry")
        return 1
    else:
        print()
        print("Subclass inference test: INDETERMINATE")
        print("No DefectCondition instances found in the graph. Check that the")
        print("ontology and sample defect data are present.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
