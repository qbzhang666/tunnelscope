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
- width='stretch' (Streamlit >= 1.49) is used for full-width tables;
  the deprecated use_container_width parameter has been migrated.
"""

import streamlit as st
import pandas as pd

from utils.ontology_loader import load_ontology, load_defects
from utils.sparql_queries import EXAMPLE_QUERIES
from utils.styling import apply_custom_css
from utils.explainers import render_plain_guide

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

render_plain_guide(
    "Ask the knowledge base direct questions — any number in the app "
    "can be verified here. Pick a question, press **Run**, read the "
    "table. The code stays tucked away unless you want it."
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
#
# Rev 11b: the OWL 2 RL reasoner activated in Rev 11 makes the property
# path also match the subclass NODES themselves (Cracks, Spalls etc.)
# because rdfs:subClassOf becomes reflexive under closure. The two
# FILTER NOT EXISTS clauses exclude any URI that has been declared as
# a class — keeping the count to genuine instances.
instance_check = """
PREFIX tun: <http://w3id.org/tunnel-dt/ontology/v1.2#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT (COUNT(DISTINCT ?d) AS ?count) WHERE {
    ?d rdf:type/rdfs:subClassOf* tun:DefectCondition .
    FILTER NOT EXISTS { ?d rdf:type owl:Class . }
    FILTER NOT EXISTS { ?d rdf:type rdfs:Class . }
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
PREFIX owl: <http://www.w3.org/2002/07/owl#>

SELECT ?defect ?type WHERE {
    ?defect rdf:type/rdfs:subClassOf* tun:DefectCondition .
    FILTER NOT EXISTS { ?defect rdf:type owl:Class . }
    FILTER NOT EXISTS { ?defect rdf:type rdfs:Class . }
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
# Question picker — plain-language labels mapped to the underlying SPARQL.
# The raw code stays available (and editable) in a collapsed expander, so
# non-specialists never have to read it.
# -----------------------------------------------------------------------------
WRITE_MY_OWN = "(Write my own SPARQL)"

QUESTION_CATALOGUE = {
    # label shown to the user: (sparql, one-line plain meaning)
    "List every recorded defect": (
        EXAMPLE_QUERIES["All defects (subclass-aware)"],
        "Every defect in the knowledge base, with its type, ring and "
        "priority.",
    ),
    "Which defects are HIGH priority?": (
        EXAMPLE_QUERIES["High priority defects"],
        "The defects needing action within 30 days, with location and "
        "estimated cost.",
    ),
    "What defects are at Ring 1247?": (
        EXAMPLE_QUERIES["All defects at Ring 1247"],
        "Everything recorded at one specific tunnel ring.",
    ),
    "Show the cause-and-effect chain for defect D-1247-L": (
        EXAMPLE_QUERIES["FMEA chain for D-1247-L"],
        "One defect's FMEA links: component, mechanism, evidence, cause "
        "and repair.",
    ),
    "How many defects has each sensor type detected?": (
        EXAMPLE_QUERIES["Modality coverage stats"],
        "Defect counts per sensing source (photo, depth, thermal, radar).",
    ),
    "Which defects still lack root-cause evidence?": (
        EXAMPLE_QUERIES["Defects missing cause-level evidence"],
        "Defects whose FMEA chain is incomplete — candidates for "
        "follow-up survey.",
    ),
    "Which standards do the prescribed repairs come from?": (
        EXAMPLE_QUERIES["Interventions per standard"],
        "Repair counts per source standard (Austroads, AASHTO, ...).",
    ),
    "Which tunnel rings have recorded defects?": (
        DIAGNOSTIC_QUERIES["Instances — distinct ring IDs in the graph"],
        "The distinct ring numbers that appear in the defect records.",
    ),
    "How many records of each type?": (
        DIAGNOSTIC_QUERIES["Instances — count by class (ABox)"],
        "Record counts per concept type.",
    ),
    "What concept types does the system know?": (
        DIAGNOSTIC_QUERIES["Schema — list all OWL classes"],
        "The knowledge base's vocabulary: every defect, cause and repair "
        "concept, with descriptions.",
    ),
    "How do the concepts relate to each other?": (
        DIAGNOSTIC_QUERIES["Schema — list all object properties (with domain/range)"],
        "Every relationship type (e.g. 'has cause', 'detected by') and "
        "what it connects.",
    ),
    "Show the concept family tree": (
        DIAGNOSTIC_QUERIES["Schema — class hierarchy (subclass relationships)"],
        "Which concept sits under which (e.g. Cracks is a kind of "
        "DefectCondition).",
    ),
    "Which relationship types are most used in the data?": (
        DIAGNOSTIC_QUERIES["Schema — count triples by predicate"],
        "A usage count of every relationship type — a health check of "
        "the graph.",
    ),
}

question = st.selectbox(
    "Pick a question to ask the knowledge base",
    options=list(QUESTION_CATALOGUE.keys()) + [WRITE_MY_OWN],
    index=0,
    help="Each option is a ready-made query. The SPARQL it runs is in "
         "the expander below — visible if you want it, ignorable if not.",
)

if question == WRITE_MY_OWN:
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
else:
    default_query, _meaning = QUESTION_CATALOGUE[question]
    st.caption(f"❓ **Asks:** {_meaning}")

# -----------------------------------------------------------------------------
# Query editor — collapsed unless the user is writing their own
# -----------------------------------------------------------------------------
with st.expander("✏️ SPARQL code (view or edit — for specialists)",
                 expanded=(question == WRITE_MY_OWN)):
    st.caption(
        "SPARQL is the knowledge base's query language — like SQL for "
        "databases. The `PREFIX` lines are address shorthand; the "
        "question itself is the `SELECT ... WHERE { ... }` part."
    )
    query = st.text_area(
        "SPARQL query",
        value=default_query,
        height=260,
        help="Edit freely and click Run query below.",
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
                            pred_df, width="stretch", hide_index=True
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
                            cls_df, width="stretch", hide_index=True
                        )
                except Exception as e:
                    st.markdown(f":grey[Diagnostic failed: {e}]")
        else:
            st.success(f"Query returned **{len(df)} rows**.")
            st.dataframe(df, width="stretch", hide_index=True)

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
    - `tun:hasPotentialCause`, `tun:hasIntervention`
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
