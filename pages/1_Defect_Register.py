"""
Defect Register — page 1
========================

Ranked list of all defects in the active tunnel, with filtering by
priority, type, and completeness. Clicking a defect navigates to the
Defect Detail page.
"""

import streamlit as st
import pandas as pd

from utils.ontology_loader import load_ontology, load_defects
from utils.styling import apply_custom_css

st.set_page_config(page_title="Defect Register", layout="wide")
apply_custom_css()

# Ensure ontology is loaded
if "graph" not in st.session_state:
    st.session_state.graph = load_ontology()
    st.session_state.defects = load_defects(st.session_state.graph)

st.title("Defect register")
st.caption(
    "All detected defects across the active tunnel, ranked by priority. "
    "Filter and sort, then click **View** to see the full FMEA chain."
)

defects = st.session_state.defects

# -----------------------------------------------------------------------------
# Filters
# -----------------------------------------------------------------------------
with st.expander("Filters", expanded=True):
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        type_filter = st.multiselect(
            "Defect type",
            options=sorted(set(d["defect_type"] for d in defects)),
            default=[],
        )
    with col2:
        priority_filter = st.multiselect(
            "Priority",
            options=["HIGH", "MEDIUM", "LOW"],
            default=[],
        )
    with col3:
        min_completeness = st.slider(
            "Min. FMEA completeness",
            min_value=0.0, max_value=1.0,
            value=0.0, step=0.25,
        )
    with col4:
        sort_by = st.selectbox(
            "Sort by",
            options=["Priority + completeness", "Chainage", "Cost (high-low)",
                    "Date discovered"],
            index=0,
        )

# Apply filters
filtered = [
    d for d in defects
    if (not type_filter or d["defect_type"] in type_filter)
    and (not priority_filter or d.get("priority") in priority_filter)
    and d.get("completeness_score", 0) >= min_completeness
]

# Apply sort
if sort_by == "Priority + completeness":
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    filtered.sort(
        key=lambda d: (
            priority_order.get(d.get("priority"), 3),
            -d.get("completeness_score", 0),
        )
    )
elif sort_by == "Chainage":
    filtered.sort(key=lambda d: d.get("chainage_m", 0))
elif sort_by == "Cost (high-low)":
    filtered.sort(key=lambda d: -d.get("estimated_cost_aud", 0))
elif sort_by == "Date discovered":
    filtered.sort(key=lambda d: d.get("discovered_on", ""), reverse=True)

st.write(f"**{len(filtered)} defects** match current filters.")

# -----------------------------------------------------------------------------
# Defect table
# -----------------------------------------------------------------------------
if filtered:
    table_data = []
    for d in filtered:
        score = d.get("completeness_score", 0)
        completeness_str = f"{int(score * 4)}/4"
        cost = d.get("estimated_cost_aud", 0)
        cost_str = f"${cost:,}" if cost else "pending"

        table_data.append({
            "ID": d["defect_id"],
            "Description": d["description"],
            "Location": f"Ring {d['ring_id']} · K{d['chainage_m']:.0f}m · {d['position']}",
            "Type": d["defect_type"],
            "Priority": d.get("priority", "—"),
            "Completeness": completeness_str,
            "Est. cost": cost_str,
        })

    df = pd.DataFrame(table_data)

    # Streamlit native dataframe with selection
    event = st.dataframe(
        df,
        width='stretch',
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "ID": st.column_config.TextColumn(width="small"),
            "Priority": st.column_config.TextColumn(width="small"),
            "Completeness": st.column_config.TextColumn(width="small"),
            "Est. cost": st.column_config.TextColumn(width="small"),
        },
    )

    # Handle selection — navigate to detail page
    if event.selection.rows:
        selected_idx = event.selection.rows[0]
        selected_defect = filtered[selected_idx]
        st.session_state.selected_defect_id = selected_defect["defect_id"]
        st.info(
            f"Selected **{selected_defect['defect_id']}** — "
            f"open the **Defect Detail** page in the sidebar to view "
            f"the full FMEA chain."
        )
else:
    st.info("No defects match the current filters.")

# -----------------------------------------------------------------------------
# Export
# -----------------------------------------------------------------------------
st.divider()
col1, col2 = st.columns(2)
with col1:
    if filtered:
        csv = pd.DataFrame(filtered).to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download filtered list (CSV)",
            csv,
            file_name="defect_register.csv",
            mime="text/csv",
        )
with col2:
    if filtered:
        import json
        jsonstr = json.dumps(filtered, indent=2).encode("utf-8")
        st.download_button(
            "Download as JSON",
            jsonstr,
            file_name="defect_register.json",
            mime="application/json",
        )
