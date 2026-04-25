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

st.set_page_config(page_title="Ontology Browser", layout="wide")
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

tab1, tab2, tab3, tab4 = st.tabs([
    "Class hierarchy", "Object properties", "Data properties", "Individuals",
])

# -----------------------------------------------------------------------------
# Class hierarchy
# -----------------------------------------------------------------------------
with tab1:
    st.markdown("### Class hierarchy")

    # Build hierarchy tree
    def get_children(parent):
        return sorted([
            c for c in graph.subjects(RDFS.subClassOf, parent)
            if not str(c).startswith("http://www.w3.org/")
        ])

    def display_class(cls, depth=0):
        label = str(cls).split("#")[-1] if "#" in str(cls) else str(cls)
        indent = "&nbsp;" * (depth * 4)
        comment = list(graph.objects(cls, RDFS.comment))
        comment_text = f" — *{str(comment[0])}*" if comment else ""
        st.markdown(f"{indent}• **{label}**{comment_text}",
                    unsafe_allow_html=True)

        for child in get_children(cls):
            display_class(child, depth + 1)

    # Find root classes (no parent or parent is owl:Thing)
    root_classes = [
        c for c in classes
        if not list(graph.objects(c, RDFS.subClassOf))
        or all(str(p) == str(OWL.Thing) for p in graph.objects(c, RDFS.subClassOf))
    ]
    root_classes = [c for c in root_classes if "#" in str(c)]

    if root_classes:
        for root in sorted(root_classes, key=str):
            display_class(root)
    else:
        st.info("No class hierarchy found. Is the ontology file loaded?")

# -----------------------------------------------------------------------------
# Object properties
# -----------------------------------------------------------------------------
with tab2:
    st.markdown("### Object properties")
    st.caption("Relations between individuals (e.g., hasCause, atComponent).")

    for prop in sorted(obj_props, key=str):
        if not "#" in str(prop):
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

# -----------------------------------------------------------------------------
# Data properties
# -----------------------------------------------------------------------------
with tab3:
    st.markdown("### Data properties")
    st.caption("Attributes of individuals (e.g., crackWidth, chainageM).")

    for prop in sorted(data_props, key=str):
        if not "#" in str(prop):
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

# -----------------------------------------------------------------------------
# Individuals
# -----------------------------------------------------------------------------
with tab4:
    st.markdown("### Named individuals (ABox)")
    st.caption("Specific defect instances, components, and interventions.")

    # Group by type
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
