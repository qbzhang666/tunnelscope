"""
SPARQL Console — page 3
========================

Direct query interface to the populated ontology graph. Runs in-process
via rdflib — in production this connects to Apache Jena Fuseki.

REVISED:
- Namespace updated to http://w3id.org/tunnel-dt/ontology/v1.2#
- Honest banner explaining what's in the graph vs what's in the JSON
  fallback (the source of the "no results" issue).
- Diagnostic queries that focus on the schema (TBox), which is always
  populated, in addition to instance queries (ABox) which may not be
  if defects are loaded from data/*.json.
- use_container_width=True replaces width='stretch' (Streamlit < 1.49
  compatibility on Cloud).
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
    "Direct query interface to the populated ontology graph. Runs "
    "in-process via rdflib — in production this connects to Apache "
    "Jena Fuseki."
)

# -----------------------------------------------------------------------------
# Honest banner about graph contents
# -----------------------------------------------------------------------------
graph = st.session_state.graph
graph_size = len(graph)

# Check whether the graph has any defect *instances*, not just classes.
# Uses rdf:type/rdfs:subClassOf* so subclass-typed defects (Cracks,
# Spalls, LeakingJoints, ...) are counted alongside ones typed directly
# as DefectCondition. Without the property path, rdflib counts only
# direct-typed instances and misses the rest.
instance_check = """
PREFIX tun: <http://w3id.org/tunnel-dt/ontology/v1.2#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT (COUNT(DISTINCT ?d) AS ?count) WHERE {
    ?d rdf:type/rdfs:subClassOf* tun:DefectCondition .
}
"""
try:
    rows = list(graph.query(instance_check))
    instance_count = int(rows[0][0]) if rows else 0
except Exception:
    instance_count = 0

defect_dict_count = len(st.session_state.get("defects", []))

if instance_count == 0 and defect_dict_count > 0:
    st.info(
        f"**Graph status:** {graph_size:,} triples loaded — schema (TBox) "
        f"only, no defect instances (ABox) materialised. The {defect_dict_count} "
        f"defects shown on the **Defect Register** are loaded from "
        f"`data/defects_tunnel_a.json` as a fallback. SPARQL queries can "
        f"explore the schema (classes, properties, hierarchy) but will "
        f"not return defect instances. To enable instance queries, see "
        f"`materialise_defects_into_graph()` in the deployment notes."
    )
else:
    st.caption(
        f"Graph: **{graph_size:,} triples** · "
        f"**{instance_count} defect instance(s)** materialised."
    )

# -----------------------------------------------------------------------------
# Diagnostic queries — focus on the schema (always present)
# -----------------------------------------------------------------------------
DIAGNOSTIC_QUERIES = {
    "Schema — list all OWL classes": """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?class ?comment WHERE {
    ?class rdf:type owl:Class .
    OPTIONAL { ?class rdfs:comment ?comment . }
    FILTER(STRSTARTS(STR(?class), "http://w3id.org/tunnel-dt/"))
}
ORDER BY ?class
""",
    "Schema — list all object properties (with domain/range)": """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?property ?domain ?range WHERE {
    ?property rdf:type owl:ObjectProperty .
    OPTIONAL { ?property rdfs:domain ?domain . }
    OPTIONAL { ?property rdfs:range ?range . }
    FILTER(STRSTARTS(STR(?property), "http://w3id.org/tunnel-dt/"))
}
ORDER BY ?property
""",
    "Schema — count triples by predicate": """SELECT ?predicate (COUNT(*) AS ?count) WHERE {
    ?s ?predicate ?o .
}
GROUP BY ?predicate
ORDER BY DESC(?count)
LIMIT 30
""",
    "Schema — class hierarchy (subclass relationships)": """PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?child ?parent WHERE {
    ?child rdfs:subClassOf ?parent .
    FILTER(STRSTARTS(STR(?child), "http://w3id.org/tunnel-dt/"))
    FILTER(STRSTARTS(STR(?parent), "http://w3id.org/tunnel-dt/"))
}
ORDER BY ?parent ?child
""",
    "Instances — list all defect instances (subclass-aware)": """PREFIX tun: <http://w3id.org/tunnel-dt/ontology/v1.2#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?defect ?type WHERE {
    ?defect rdf:type/rdfs:subClassOf* tun:DefectCondition .
    OPTIONAL { ?defect tun:hasType ?type . }
}
ORDER BY ?defect
LIMIT 50
""",
    "Instances — distinct ring IDs in the graph": """PREFIX tun: <http://w3id.org/tunnel-dt/ontology/v1.2#>

SELECT DISTINCT ?ring WHERE {
    ?defect tun:atRingID ?ring .
}
ORDER BY ?ring
""",
    "Instances — count by class (ABox)": """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>

SELECT ?class (COUNT(?instance) AS ?count) WHERE {
    ?instance rdf:type ?class .
    FILTER(?class != owl:NamedIndividual)
    FILTER(STRSTARTS(STR(?class), "http://w3id.org/tunnel-dt/"))
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
    help="Schema queries (top of list) work against any loaded ontology. "
         "Instance queries require defects to be materialised in the graph.",
)

if example_name != "(Write my own)":
    default_query = all_examples[example_name]
else:
    default_query = """PREFIX tun: <http://w3id.org/tunnel-dt/ontology/v1.2#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>

SELECT ?class WHERE {
    ?class rdf:type owl:Class .
    FILTER(STRSTARTS(STR(?class), "http://w3id.org/tunnel-dt/"))
}
LIMIT 20
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
# Helpers
# -----------------------------------------------------------------------------
def _shorten(val):
    if val is None:
        return ""
    s = str(val)
    if "#" in s:
        return ":" + s.split("#")[-1]
    if "/" in s and s.startswith("http"):
        return s.rsplit("/", 1)[-1]
    return s


def _run_to_dataframe(g, sparql: str) -> pd.DataFrame:
    """Execute a SPARQL query and return a DataFrame with shortened URIs."""
    results = list(g.query(sparql))
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
    try:
        df = _run_to_dataframe(graph, query)

        if df.empty:
            st.warning(
                "Query returned no results. If you queried for defect "
                "instances and the graph banner above shows zero "
                "instances materialised, that's why — the schema is "
                "loaded but the instances live in JSON. Try a schema "
                "query (top of the dropdown) instead."
            )

            with st.expander("🔍 What *is* in the graph?", expanded=True):
                st.markdown(f"**Total triples:** {graph_size:,}")

                st.markdown("**Top 10 most-used predicates:**")
                try:
                    pred_df = _run_to_dataframe(graph, """
                        SELECT ?p (COUNT(*) AS ?count) WHERE {
                            ?s ?p ?o .
                        }
                        GROUP BY ?p
                        ORDER BY DESC(?count)
                        LIMIT 10
                    """)
                    if pred_df.empty:
                        st.markdown(":grey[Graph is empty.]")
                    else:
                        st.dataframe(
                            pred_df, use_container_width=True, hide_index=True
                        )
                except Exception as e:
                    st.markdown(f":grey[Diagnostic failed: {e}]")

                st.markdown("**Classes defined in the graph:**")
                try:
                    cls_df = _run_to_dataframe(graph, """
                        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                        PREFIX owl: <http://www.w3.org/2002/07/owl#>
                        SELECT ?class WHERE { ?class rdf:type owl:Class . }
                        ORDER BY ?class
                        LIMIT 30
                    """)
                    if cls_df.empty:
                        st.markdown(":grey[No OWL classes in the graph.]")
                    else:
                        st.dataframe(
                            cls_df, use_container_width=True, hide_index=True
                        )
                except Exception as e:
                    st.markdown(f":grey[Diagnostic failed: {e}]")
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
    - `tun:` — `http://w3id.org/tunnel-dt/ontology/v1.2#`
    - `cobie:` — `http://w3id.org/tunnel-dt/cobie#`
    - `rdf:` — `http://www.w3.org/1999/02/22-rdf-syntax-ns#`
    - `rdfs:` — `http://www.w3.org/2000/01/rdf-schema#`
    - `owl:` — `http://www.w3.org/2002/07/owl#`

    **Useful classes (TBox):**
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

    **Schema vs instances:**
    The graph always contains the schema (TBox) — classes, properties,
    hierarchy. Defect instances (ABox) are only in the graph if the
    ontology TTL contains them, OR if the loader materialises them
    from JSON. If your graph has zero defect instances, schema queries
    still work; instance queries return empty.
    """)
