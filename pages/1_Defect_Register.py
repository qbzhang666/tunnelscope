"""
Defect Register — page 1
========================

Ranked list of all defects in the active tunnel, with filtering by
priority, type, and evidence breadth. Clicking a defect navigates to the
Defect Detail page.

REVISED:
- width='stretch' replaced with use_container_width=True (compatibility
  with Streamlit < 1.49 on Cloud).
- New "Evidence" column shows how many of the four modalities have data,
  framed neutrally rather than as a deficiency score.
- Defects ingested via the Ingest page are merged into the listing.
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
    "All detected defects across the active tunnel. Filter and sort, "
    "then click a row to select. Evidence breadth (how many modalities "
    "informed the record) is shown but does not gate intervention."
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
        source_filter = st.multiselect(
            "Source",
            options=["Ontology", "Ingested (this session)"],
            default=[],
            help="Filter by whether a defect came from the ontology or "
                 "was uploaded on the Ingest page.",
        )
    with col4:
        sort_by = st.selectbox(
            "Sort by",
            options=["Priority", "Chainage", "Cost (high-low)",
                     "Date discovered", "Evidence breadth"],
            index=0,
        )

# Apply filters
def _passes_source_filter(defect):
    if not source_filter:
        return True
    is_ingested = defect.get("ingested", False)
    if "Ingested (this session)" in source_filter and is_ingested:
        return True
    if "Ontology" in source_filter and not is_ingested:
        return True
    return False

filtered = [
    d for d in defects
    if (not type_filter or d["defect_type"] in type_filter)
    and (not priority_filter or d.get("priority") in priority_filter)
    and _passes_source_filter(d)
]

# Apply sort
if sort_by == "Priority":
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
elif sort_by == "Evidence breadth":
    filtered.sort(key=lambda d: -d.get("completeness_score", 0))

st.write(f"**{len(filtered)} defects** match current filters.")

# -----------------------------------------------------------------------------
# Defect table
# -----------------------------------------------------------------------------
if filtered:
    table_data = []
    for d in filtered:
        # Count modalities with evidence (out of 4) instead of showing a
        # completeness score that suggests deficiency.
        evidence = d.get("modality_evidence", {})
        modality_count = sum(
            1 for m in ["RGB", "RGBD", "Thermal", "GPR"]
            if evidence.get(m)
        )
        evidence_str = f"{modality_count}/4 modalities"

        cost = d.get("estimated_cost_aud", 0)
        cost_str = f"${cost:,}" if cost else "pending"

        source = "Ingested" if d.get("ingested") else "Ontology"

        table_data.append({
            "ID": d["defect_id"],
            "Description": d["description"],
            "Location": (
                f"Ring {d['ring_id']} · "
                f"K{d.get('chainage_m', 0):.0f}m · "
                f"{d.get('position', '—')}"
            ),
            "Type": d["defect_type"],
            "Priority": d.get("priority", "—"),
            "Evidence": evidence_str,
            "Source": source,
            "Est. cost": cost_str,
        })

    df = pd.DataFrame(table_data)

    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "ID": st.column_config.TextColumn(width="small"),
            "Priority": st.column_config.TextColumn(width="small"),
            "Evidence": st.column_config.TextColumn(width="small"),
            "Source": st.column_config.TextColumn(width="small"),
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
        jsonstr = json.dumps(filtered, indent=2, default=str).encode("utf-8")
        st.download_button(
            "Download as JSON",
            jsonstr,
            file_name="defect_register.json",
            mime="application/json",
        )
