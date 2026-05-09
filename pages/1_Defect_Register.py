"""
Defect Register — page 1
========================

Ranked list of all defects in the active tunnel network, with a
geographic overview map and filters by priority, type, and source.

REVISED (Rev 6):
- Overview map at the top — both tunnels rendered, defect markers
  coloured by priority. Tunnel and table stay in sync via the same
  filter controls.
- Click a marker on the map → defect ID is captured for the Defect
  Detail page navigation.
"""

import streamlit as st
import pandas as pd
from streamlit_folium import st_folium

from utils.ontology_loader import load_ontology, load_defects
from utils.styling import apply_custom_css
from utils.gis import build_overview_map, list_tunnels

st.set_page_config(page_title="Defect Register", layout="wide")
apply_custom_css()

if "graph" not in st.session_state:
    st.session_state.graph = load_ontology()
    st.session_state.defects = load_defects(st.session_state.graph)

st.title("Defect register")
st.caption(
    "All detected defects across the active tunnel network. **Filters** "
    "(below) drive both the map markers and the table contents. **Row "
    "selection** (the checkboxes in the table) is for actions — pick "
    "one row to navigate to Defect Detail, or several to bulk-delete."
)

defects = list(st.session_state.defects)  # copy so filters don't mutate state
ingested_count = sum(1 for d in defects if d.get("ingested"))

# -----------------------------------------------------------------------------
# Filters
# -----------------------------------------------------------------------------
tunnels = list_tunnels()
tunnel_id_to_label = {t["tunnel_id"]: t["label"] for t in tunnels}

with st.expander("Filters", expanded=True):
    col1, col2, col3, col4, col5 = st.columns(5)

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
        tunnel_filter = st.multiselect(
            "Tunnel",
            options=[t["tunnel_id"] for t in tunnels],
            format_func=lambda x: tunnel_id_to_label.get(x, x),
            default=[],
        )
    with col4:
        source_filter = st.multiselect(
            "Source",
            options=["Ontology", "Ingested (this session)"],
            default=[],
        )
    with col5:
        sort_by = st.selectbox(
            "Sort by",
            options=["Priority", "Chainage", "Cost (high-low)",
                     "Date discovered", "Evidence breadth"],
            index=0,
        )


def _passes_source_filter(defect):
    if not source_filter:
        return True
    is_ingested = defect.get("ingested", False)
    if "Ingested (this session)" in source_filter and is_ingested:
        return True
    if "Ontology" in source_filter and not is_ingested:
        return True
    return False


def _passes_tunnel_filter(defect):
    if not tunnel_filter:
        return True
    return defect.get("tunnel_id") in tunnel_filter


filtered = [
    d for d in defects
    if (not type_filter or d["defect_type"] in type_filter)
    and (not priority_filter or d.get("priority") in priority_filter)
    and _passes_source_filter(d)
    and _passes_tunnel_filter(d)
]

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

st.write(
    f"**{len(filtered)} defects** match current filters."
    + (f" · {ingested_count} ingested this session." if ingested_count else "")
)

# -----------------------------------------------------------------------------
# Overview map
# -----------------------------------------------------------------------------
st.subheader("Geographic overview")

selected_tunnel_for_map = tunnel_filter[0] if len(tunnel_filter) == 1 else None
m = build_overview_map(
    filtered,
    selected_tunnel_id=selected_tunnel_for_map,
    height=420,
)
# Key the map so it rebuilds when defects are added/removed or filters
# change — without this, st_folium returns the cached previous render
# and newly-ingested defects appear to be missing.
map_key = (
    f"register_overview_map_"
    f"{len(defects)}_{len(filtered)}_"
    f"{'-'.join(tunnel_filter) or 'all'}_"
    f"{'-'.join(priority_filter) or 'all'}"
)
map_state = st_folium(
    m,
    width=None,
    height=420,
    returned_objects=["last_object_clicked", "last_object_clicked_tooltip"],
    key=map_key,
)

# If the user clicked a defect marker, capture the ID for Defect Detail
clicked_tooltip = map_state.get("last_object_clicked_tooltip") if map_state else None
if clicked_tooltip and clicked_tooltip in {d["defect_id"] for d in filtered}:
    st.session_state.selected_defect_id = clicked_tooltip
    st.info(
        f"Selected **{clicked_tooltip}** from the map — open the "
        f"**Defect Detail** page in the sidebar to view the FMEA chain."
    )

st.divider()

# -----------------------------------------------------------------------------
# Defect table
# -----------------------------------------------------------------------------
st.subheader("Defect list")

if filtered:
    table_data = []
    for d in filtered:
        evidence = d.get("modality_evidence", {})
        modality_count = sum(
            1 for m in ["RGB", "RGBD", "Thermal", "GPR"]
            if evidence.get(m)
        )
        evidence_str = f"{modality_count}/4 modalities"

        cost = d.get("estimated_cost_aud", 0)
        cost_str = f"${cost:,}" if cost else "pending"

        source = "Ingested" if d.get("ingested") else "Ontology"
        tunnel_label = tunnel_id_to_label.get(d.get("tunnel_id"), "—")

        table_data.append({
            "ID": d["defect_id"],
            "Tunnel": tunnel_label,
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

    # Multi-row selection enables both navigation (single tick → set
    # selected_defect_id) and bulk deletion (multiple ticks → delete).
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
        column_config={
            "ID": st.column_config.TextColumn(width="small"),
            "Tunnel": st.column_config.TextColumn(width="small"),
            "Priority": st.column_config.TextColumn(width="small"),
            "Evidence": st.column_config.TextColumn(width="small"),
            "Source": st.column_config.TextColumn(width="small"),
            "Est. cost": st.column_config.TextColumn(width="small"),
        },
    )

    selected_rows = event.selection.rows if event.selection else []
    selected_defects = [filtered[i] for i in selected_rows]
    selected_ids = [d["defect_id"] for d in selected_defects]

    # ---- Selection summary + actions ----
    if selected_defects:
        if len(selected_defects) == 1:
            d = selected_defects[0]
            st.session_state.selected_defect_id = d["defect_id"]
            st.info(
                f"Selected **{d['defect_id']}** — open **Defect Detail** "
                f"in the sidebar to view the full FMEA chain, or use the "
                f"actions below."
            )
        else:
            st.info(
                f"**{len(selected_defects)} defects selected** "
                f"({', '.join(selected_ids[:5])}"
                f"{'…' if len(selected_ids) > 5 else ''}). "
                f"Selecting multiple rows is for bulk actions like "
                f"deletion or export — Defect Detail uses only the first."
            )

        # ---- Delete UX with mandatory confirmation ----
        with st.container(border=True):
            st.markdown("**Delete selected defects**")

            # Show breakdown so the operator sees what they're about to delete
            ingested_to_del = [d for d in selected_defects if d.get("ingested")]
            ontology_to_del = [d for d in selected_defects if not d.get("ingested")]

            if ingested_to_del:
                st.markdown(
                    f"- **{len(ingested_to_del)} ingested** (this session): "
                    f"{', '.join(d['defect_id'] for d in ingested_to_del[:5])}"
                    f"{'…' if len(ingested_to_del) > 5 else ''}"
                )
            if ontology_to_del:
                st.warning(
                    f"⚠️ **{len(ontology_to_del)} from the ontology / "
                    f"sample data:** "
                    f"{', '.join(d['defect_id'] for d in ontology_to_del[:5])}"
                    f"{'…' if len(ontology_to_del) > 5 else ''}. "
                    f"These are demo defects — deleting them only removes "
                    f"them from this session, not from the JSON file. "
                    f"They will reappear after a server reboot."
                )

            confirm = st.checkbox(
                f"I confirm I want to delete these "
                f"{len(selected_defects)} defect(s)",
                key="delete_confirm_checkbox",
            )
            delete_clicked = st.button(
                "Delete selected",
                type="primary",
                disabled=not confirm,
                key="delete_button",
            )

            if delete_clicked and confirm:
                ids_to_delete = set(selected_ids)

                # Remove from session-state defects (the merged list)
                st.session_state.defects = [
                    d for d in st.session_state.defects
                    if d["defect_id"] not in ids_to_delete
                ]
                # Remove from ingested-this-session list (so the Ingest
                # page counter and "registered this session" panel
                # also update)
                st.session_state.ingested_defects = [
                    d for d in st.session_state.get("ingested_defects", [])
                    if d["defect_id"] not in ids_to_delete
                ]
                # Clear selected_defect_id if it was one of the deleted
                if st.session_state.get("selected_defect_id") in ids_to_delete:
                    st.session_state.selected_defect_id = None

                st.success(
                    f"Deleted **{len(ids_to_delete)} defect(s)**: "
                    f"{', '.join(sorted(ids_to_delete))}"
                )
                # Force a fresh render so the table and map drop the rows
                st.rerun()
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
