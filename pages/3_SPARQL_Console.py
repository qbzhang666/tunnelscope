"""
SPARQL Console — page 3
========================

Direct query interface to the populated ontology. Users can select
pre-built queries from a dropdown, or write their own. Results are
displayed as an interactive table.
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
# Example query selector
# -----------------------------------------------------------------------------
example_name = st.selectbox(
    "Load example query",
    options=["(Write my own)"] + list(EXAMPLE_QUERIES.keys()),
    index=1,
)

if example_name != "(Write my own)":
    default_query = EXAMPLE_QUERIES[example_name]
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

col1, col2, col3 = st.columns([1, 1, 6])
with col1:
    run = st.button("Run query", type="primary")
with col2:
    if st.button("Reset"):
        st.rerun()

# -----------------------------------------------------------------------------
# Execute
# -----------------------------------------------------------------------------
if run:
    graph = st.session_state.graph
    try:
        results = list(graph.query(query))

        if not results:
            st.info("Query returned no results. "
                    "Check that the ontology is populated with matching data.")
        else:
            # Extract variable names from the first result
            headers = [str(v) for v in results[0].labels] if results else []

            rows = []
            for row in results:
                row_dict = {}
                for i, val in enumerate(row):
                    header = headers[i] if i < len(headers) else f"col_{i}"
                    if val is None:
                        row_dict[header] = ""
                    else:
                        val_str = str(val)
                        # Shorten URIs for display
                        if "#" in val_str:
                            val_str = ":" + val_str.split("#")[-1]
                        row_dict[header] = val_str
                rows.append(row_dict)

            df = pd.DataFrame(rows)
            st.success(f"Query returned **{len(df)} rows**.")
            st.dataframe(df, width='stretch', hide_index=True)

            # Export options
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
    """)
