"""
Ontology Browser — page 5
=========================

Displays the class hierarchy, object properties, and SWRL rules of the
populated ontology. Lets users inspect the TBox without needing Protégé.
"""

import streamlit as st
from rdflib import RDF, RDFS, OWL

from utils.ontology_loader import load_ontology, TUN
from utils.styling import apply_custom_css
from utils.explainers import render_plain_guide

apply_custom_css()

if "graph" not in st.session_state:
    st.session_state.graph = load_ontology()

graph = st.session_state.graph

st.title("Ontology browser")
st.caption(
    "Browse the class hierarchy, object properties, and axioms of the "
    "populated ontology. Useful for understanding the schema without "
    "opening Protégé."
)

render_plain_guide(
    "The system's dictionary — every defect type, cause and repair it "
    "reasons with. Curated engineering knowledge, not a black box."
)

# -----------------------------------------------------------------------------
# Stats
# -----------------------------------------------------------------------------
classes = list(graph.subjects(RDF.type, OWL.Class))
obj_props = list(graph.subjects(RDF.type, OWL.ObjectProperty))
data_props = list(graph.subjects(RDF.type, OWL.DatatypeProperty))
individuals = list(graph.subjects(RDF.type, OWL.NamedIndividual))

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Classes", len(classes))
with col2:
    st.metric("Object properties", len(obj_props))
with col3:
    st.metric("Data properties", len(data_props))
with col4:
    st.metric("Individuals", len(individuals))

if any(len(x) == 0 for x in [classes, obj_props, data_props]):
    st.warning(
        "One or more of the metric counts is zero. The ontology may not "
        "have loaded correctly. Check that `ontology/tunnel_maintenance.ttl` "
        "exists and parses as Turtle."
    )

tab1, tab2, tab3, tab4 = st.tabs([
    "Class hierarchy", "Object properties", "Data properties", "Individuals",
])

with tab1:
    st.markdown("### Class hierarchy")

    def _get_children(parent):
        return sorted([
            c for c in graph.subjects(RDFS.subClassOf, parent)
            if not str(c).startswith("http://www.w3.org/")
        ], key=str)

    def _render_class_html(cls, path=None):
        """
        Return an HTML string for a class and its descendants.
        Uses path-based cycle detection to handle reflexive rdfs:subClassOf
        triples introduced by the OWL 2 RL reasoner (a class is its own
        subclass), which would otherwise cause infinite recursion.
        """
        if path is None:
            path = frozenset()
        if cls in path:
            return ""

        new_path = path | {cls}
        label = str(cls).split("#")[-1] if "#" in str(cls) else str(cls).split("/")[-1]
        comment = list(graph.objects(cls, RDFS.comment))
        comment_html = (
            f" <em style='color:#5F5E5A;font-size:15px'>{str(comment[0])}</em>"
            if comment else ""
        )

        children = [c for c in _get_children(cls) if c not in new_path]

        if children:
            children_html = "".join(_render_class_html(c, new_path) for c in children)
            return (
                f'<details style="margin:3px 0">'
                f'<summary style="cursor:pointer;padding:3px 0;font-size:16px">'
                f'<strong>{label}</strong>{comment_html}'
                f'</summary>'
                f'<div style="margin-left:1.5rem;border-left:2px solid #E5E4DE;padding-left:0.75rem">'
                f'{children_html}'
                f'</div>'
                f'</details>'
            )
        else:
            return (
                f'<div style="margin:3px 0;padding:3px 0;font-size:16px">'
                f'&#8226; <strong>{label}</strong>{comment_html}'
                f'</div>'
            )

    root_classes = [
        c for c in classes
        if not list(graph.objects(c, RDFS.subClassOf))
        or all(str(p) == str(OWL.Thing) for p in graph.objects(c, RDFS.subClassOf))
    ]
    root_classes = [c for c in root_classes if "#" in str(c)]

    if root_classes:
        tree_html = "".join(_render_class_html(root) for root in sorted(root_classes, key=str))
        st.markdown(
            f'<div style="line-height:1.7">{tree_html}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("No class hierarchy found. Is the ontology file loaded?")

with tab2:
    st.markdown("### Object properties")
    st.caption("Relations between individuals (e.g., hasCause, atComponent).")

    for prop in sorted(obj_props, key=str):
        if "#" not in str(prop):
            continue
        label = str(prop).split("#")[-1]
        domain = list(graph.objects(prop, RDFS.domain))
        range_ = list(graph.objects(prop, RDFS.range))
        comment = list(graph.objects(prop, RDFS.comment))

        with st.expander(f"`{label}`"):
            if domain:
                st.markdown(f"**Domain:** `{str(domain[0]).split('#')[-1]}`")
            if range_:
                st.markdown(f"**Range:** `{str(range_[0]).split('#')[-1]}`")
            if comment:
                st.markdown(f"**Description:** {str(comment[0])}")

with tab3:
    st.markdown("### Data properties")
    st.caption("Attributes of individuals (e.g., crackWidth, chainageM).")

    for prop in sorted(data_props, key=str):
        if "#" not in str(prop):
            continue
        label = str(prop).split("#")[-1]
        domain = list(graph.objects(prop, RDFS.domain))
        range_ = list(graph.objects(prop, RDFS.range))
        comment = list(graph.objects(prop, RDFS.comment))

        with st.expander(f"`{label}`"):
            if domain:
                st.markdown(f"**Domain:** `{str(domain[0]).split('#')[-1]}`")
            if range_:
                st.markdown(f"**Range:** `{str(range_[0]).split('#')[-1]}`")
            if comment:
                st.markdown(f"**Description:** {str(comment[0])}")

with tab4:
    st.markdown("### Named individuals (ABox)")
    st.caption("Specific defect instances, components, and interventions.")

    type_groups = {}
    for ind in individuals:
        types = [t for t in graph.objects(ind, RDF.type)
                 if t != OWL.NamedIndividual and "#" in str(t)]
        for t in types:
            type_label = str(t).split("#")[-1]
            type_groups.setdefault(type_label, []).append(ind)

    for type_label in sorted(type_groups.keys()):
        inds = type_groups[type_label]
        with st.expander(f"{type_label} ({len(inds)} instances)"):
            for ind in sorted(inds, key=str)[:20]:
                label = str(ind).split("#")[-1]
                st.markdown(f"- `{label}`")
            if len(inds) > 20:
                st.caption(f"... and {len(inds) - 20} more")
