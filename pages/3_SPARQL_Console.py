"""
SPARQL Console — page 3
========================

Direct query interface to the populated ontology. Users can select
pre-built queries from a dropdown, or write their own. Results are
displayed as an interactive table.

REVISED:
- width='stretch' replaced with use_container_width=True.
- Zero-result diagnostic: when a query returns empty, the page
  automatically shows what *does* exist for the queried properties,
  so users can spot datatype mismatches and typos themselves.
- Example queries no longer hard-code a specific Ring ID — they use
  generic patterns that always return something against any populated
  ontology.
"""

import streamlit as st
import pandas as pd

from utils.ontology_loader import load_ontology, load_defects
from utils.sparql_queries import EXAMPLE_QUERIES
from utils.styling import apply_custom_css

st.set_page_config(page_title="SPARQL Console", layout="wide")
apply_custom_css()

if "graph" not in st.session_state:
    st.session_state.graph = load_ontology()
    st.session_state.defects = load_defects(st.session_state.graph)

st.title("SPARQL console")
st.caption(
    "Direct query interface to the populated ontology. Runs in-process "
    "via rdflib — in production this connects to Apache Jena Fuseki."
)

# -----------------------------------------------------------------------------
# Diagnostic queries — always work against any populated ontology
# -----------------------------------------------------------------------------
DIAGNOSTIC_QUERIES = {
    "List all defects (no filter)": """PREFIX tun: <http://tunnel-dt.transurban.com/ontology/v1.2#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?defect ?type WHERE {
    ?defect rdf:type tun:DefectCondition .
    OPTIONAL { ?defect tun:hasType ?type . }
}
LIMIT 50
""",
    "List all distinct ring IDs in the data": """PREFIX tun: <http://tunnel-dt.transurban.com/ontology/v1.2#>

SELECT DISTINCT ?ring WHERE {
    ?defect tun:atRingID ?ring .
}
ORDER BY ?ring
""",
    "List all properties used on defects": """PREFIX tun: <http://tunnel-dt.transurban.com/ontology/v1.2#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT ?property WHERE {
    ?defect rdf:type tun:DefectCondition ;
            ?property ?value .
}
ORDER BY ?property
""",
    "Count instances by class": """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?class (COUNT(?instance) AS ?count) WHERE {
    ?instance rdf:type ?class .
}
GROUP BY ?class
ORDER BY DESC(?count)
""",
}

# -----------------------------------------------------------------------------
# Example query selector
# -----------------------------------------------------------------------------
all_examples = {**DIAGNOSTIC_QUERIES, **EXAMPLE_QUERIES}

example_name = st.selectbox(
    "Load example query",
    options=["(Write my own)"] + list(all_examples.keys()),
    index=1,
    help="Diagnostic queries (top of list) always work against any "
         "populated ontology. Use them first to verify what data exists.",
)

if example_name != "(Write my own)":
    default_query = all_examples[example_name]
else:
    default_query = """PREFIX tun: <http://tunnel-dt.transurban.com/ontology/v1.2#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT ?defect ?type ?ring
WHERE {
    ?defect rdf:type tun:DefectCondition ;
            tun:hasType ?type ;
            tun:atRingID ?ring .
}
LIMIT 10
"""

# -----------------------------------------------------------------------------
# Query editor
# -----------------------------------------------------------------------------
query = st.text_area(
    "SPARQL query",
    value=default_query,
    height=260,
    help="Edit the query above and click Run.",
)

col1, col2, _ = st.columns([1, 1, 6])
with col1:
    run = st.button("Run query", type="primary")
with col2:
    if st.button("Reset"):
        st.rerun()


# -----------------------------------------------------------------------------
# Helper: shorten URIs for display
# -----------------------------------------------------------------------------
def _shorten(val):
    if val is None:
        return ""
    s = str(val)
    if "#" in s:
        return ":" + s.split("#")[-1]
    return s


def _run_to_dataframe(graph, sparql: str) -> pd.DataFrame:
    """Execute a SPARQL query and return a DataFrame with shortened URIs."""
    results = list(graph.query(sparql))
    if not results:
        return pd.DataFrame()
    headers = [str(v) for v in results[0].labels]
    rows = []
    for row in results:
        d = {}
        for i, val in enumerate(row):
            header = headers[i] if i < len(headers) else f"col_{i}"
            d[header] = _shorten(val)
        rows.append(d)
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Execute
# -----------------------------------------------------------------------------
if run:
    graph = st.session_state.graph
    try:
        df = _run_to_dataframe(graph, query)

        if df.empty:
            st.warning(
                "Query returned no results. This usually means one of: "
                "(1) a property name is misspelled, (2) a literal datatype "
                "mismatch (e.g. `1247` vs `\"1247\"`), or (3) no record "
                "matches the filter values. The diagnostic block below "
                "shows what *does* exist."
            )

            with st.expander("🔍 Diagnostic — what's actually in the graph",
                             expanded=True):
                st.markdown("**Distinct values for `tun:atRingID`:**")
                try:
                    ring_df = _run_to_dataframe(graph, """
                        PREFIX tun: <http://tunnel-dt.transurban.com/ontology/v1.2#>
                        SELECT DISTINCT ?ring WHERE { ?d tun:atRingID ?ring }
                        ORDER BY ?ring
                    """)
                    if ring_df.empty:
                        st.markdown(":grey[No `tun:atRingID` values found.]")
                    else:
                        st.dataframe(
                            ring_df, use_container_width=True, hide_index=True
                        )
                except Exception as e:
                    st.markdown(f":grey[Diagnostic query failed: {e}]")

                st.markdown("**Properties used on defects:**")
                try:
                    prop_df = _run_to_dataframe(graph, """
                        PREFIX tun: <http://tunnel-dt.transurban.com/ontology/v1.2#>
                        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                        SELECT DISTINCT ?property WHERE {
                            ?d rdf:type tun:DefectCondition ;
                               ?property ?v .
                        }
                        ORDER BY ?property
                    """)
                    if prop_df.empty:
                        st.markdown(":grey[No defect-condition properties found.]")
                    else:
                        st.dataframe(
                            prop_df, use_container_width=True, hide_index=True
                        )
                except Exception as e:
                    st.markdown(f":grey[Diagnostic query failed: {e}]")

                st.markdown(
                    "**Tip:** if your query filters by ring "
                    "(e.g. `tun:atRingID 1247`) but the diagnostic shows "
                    "rings as `\"1247\"` (quoted), the literal is stored "
                    "as a string. Try `tun:atRingID \"1247\"` instead — "
                    "or remove the `xsd:` datatype constraint."
                )
        else:
            st.success(f"Query returned **{len(df)} rows**.")
            st.dataframe(df, use_container_width=True, hide_index=True)

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "Download CSV",
                    df.to_csv(index=False).encode("utf-8"),
                    "sparql_results.csv",
                    "text/csv",
                )
            with col2:
                st.download_button(
                    "Download JSON",
                    df.to_json(orient="records", indent=2).encode("utf-8"),
                    "sparql_results.json",
                    "application/json",
                )

    except Exception as e:
        st.error(f"Query error: {e}")
        st.code(str(e), language=None)

# -----------------------------------------------------------------------------
# Query reference
# -----------------------------------------------------------------------------
with st.expander("SPARQL quick reference"):
    st.markdown("""
    **Common prefixes used in this ontology:**
    - `tun:` — `http://tunnel-dt.transurban.com/ontology/v1.2#`
    - `cobie:` — `http://tunnel-dt.transurban.com/cobie#`
    - `rdf:` — `http://www.w3.org/1999/02/22-rdf-syntax-ns#`
    - `rdfs:` — `http://www.w3.org/2000/01/rdf-schema#`
    - `owl:` — `http://www.w3.org/2002/07/owl#`

    **Useful classes:**
    - `tun:DefectCondition` — any detected defect
    - `tun:Cracks`, `tun:Spalls`, `tun:LeakingJoints` — specific types
    - `tun:FailureMechanism` — deterioration process
    - `tun:MeasuredIndicator` — observed evidence
    - `tun:PotentialCause` — root cause
    - `tun:Intervention` — prescribed repair

    **Useful properties:**
    - `tun:hasDefect`, `tun:hasMechanism`, `tun:hasIndicator`
    - `tun:hasCause`, `tun:hasIntervention`
    - `tun:atRingID`, `tun:atChainage`, `tun:atComponent`
    - `tun:detectedBy`, `tun:sourceReference`
    - `tun:completenessScore`, `tun:estimatedCost`

    **Datatype tip:** if a query returns no results, check whether your
    literal matches the stored datatype. Run *List all distinct ring IDs*
    from the diagnostic queries above to see how values are actually stored.
    """)
