import streamlit as st
import sys

st.set_page_config(page_title="Diagnostic", layout="wide")
st.title("Hello from Streamlit Cloud")
st.success("If you can see this, the platform is working.")
st.write(f"Python version: {sys.version}")
st.write(f"Streamlit version: {st.__version__}")

st.divider()
st.subheader("Try importing each project module")

modules_to_test = [
    "rdflib",
    "owlrl",
    "pandas",
    "plotly",
]

for mod in modules_to_test:
    try:
        __import__(mod)
        st.success(f"✅ `{mod}` imports successfully")
    except Exception as e:
        st.error(f"❌ `{mod}` FAILED: {e}")

st.divider()
st.subheader("Try importing project utils")

import_tests = [
    ("utils", "from utils import sparql_queries"),
    ("ontology_loader", "from utils.ontology_loader import load_ontology"),
    ("fmea_chain", "from utils.fmea_chain import compute_completeness"),
    ("cv_to_cobie", "from utils.cv_to_cobie import convert_cv_output_to_cobie_rows"),
    ("styling", "from utils.styling import apply_custom_css"),
]

for name, statement in import_tests:
    try:
        exec(statement)
        st.success(f"✅ `{name}` imports successfully")
    except Exception as e:
        st.error(f"❌ `{name}` FAILED: {e}")
        import traceback
        st.code(traceback.format_exc(), language="python")

st.divider()
st.subheader("Try loading ontology and data")

try:
    from utils.ontology_loader import load_ontology, load_defects
    g = load_ontology()
    st.success(f"✅ Ontology loaded: {len(g)} triples")
    defects = load_defects(g)
    st.success(f"✅ Defects loaded: {len(defects)} instances")
except Exception as e:
    st.error(f"❌ Data loading FAILED: {e}")
    import traceback
    st.code(traceback.format_exc(), language="python")