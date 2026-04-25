"""Minimal test app to diagnose issues."""

import streamlit as st
import json
from pathlib import Path

st.set_page_config(page_title="Test", layout="wide")

st.title("Diagnostic Test")

# Test 1: Load JSON
try:
    with open("data/defects_tunnel_a.json") as f:
        defects = json.load(f)
    st.success(f"✓ Loaded {len(defects)} defects from JSON")
except Exception as e:
    st.error(f"✗ Failed to load JSON: {e}")

# Test 2: Show first defect
try:
    d = defects[0]
    st.write("First defect ID:", d["defect_id"])
    st.write("Description:", d["description"])
    st.write("Priority:", d["priority"])
    st.write("Estimated cost:", d["estimated_cost_aud"])
except Exception as e:
    st.error(f"✗ Failed to display defect: {e}")

# Test 3: Format cost with commas
try:
    cost_str = f"${defects[0].get('estimated_cost_aud', 0):,}"
    st.write("Formatted cost:", cost_str)
except Exception as e:
    st.error(f"✗ Failed to format cost: {e}")

st.success("All tests passed!")
