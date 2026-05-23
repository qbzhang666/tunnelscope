"""
Defect Register — page 1
========================

Ranked list of all defects in the active tunnel network, with a
geographic overview map and filters by priority, type, and source.

REVISED (Rev 6d):
- Switched from st.dataframe row selection to st.data_editor with a
  leading Select checkbox column. This enables a true "Select all
  visible" toggle, which the dataframe widget can't support.
- Selection now drives DOWNLOADS, not deletion. Buttons rename to
  "Download selected (N)" with a fallback of "Download all filtered"
  when nothing is ticked.
- Deletion is moved into a small popover at the bottom of the page
  with an @st.dialog confirmation. No more bordered panel
  intruding on the main flow.
- Filters → drive map markers AND table contents (visibility).
- Selection → drives actions (download, delete). Independent of map.
"""

import json

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

# Versioning key so we can force the editor to remount after deletes.
# Without this, the data_editor would hold onto stale row keys and
# show ghost selections.
if "register_editor_version" not in st.session_state:
    st.session_state.register_editor_version = 0


st.title("Defect register")
st.caption(
    "All detected defects across the active tunnel network. **Filters** "
    "(below) drive both the map markers and the table contents. **Row "
    "selection** (the checkboxes in the table's first column) is for "
    "actions — primarily downloading the selected subset. A subtle "
    "delete option is available at the bottom of the page."
)

defects = list(st.session_state.defects)
ingested_count = sum(1 for d in defects if d.get("ingested"))

# -----------------------------------------------------------------------------
# Filters
# -----------------------------------------------------------------------------
tunnels = list_tunnels()
tunnel_id_to_label = {t["tunnel_id"]: t["label"] for t in tunnels}

with st.expander("Filters", expanded=True):
    col1, col2, col3 = st.columns(3)

    with col1:
        type_filter = st.multiselect(
            "Defect type",
            options=sorted(set(d["defect_type"] for d in defects)),
            default=[],
            placeholder="All types",
        )
    with col2:
        priority_filter = st.multiselect(
            "Priority",
            options=["HIGH", "MEDIUM", "LOW"],
            default=[],
            placeholder="All priorities",
        )
    with col3:
        tunnel_filter = st.multiselect(
            "Tunnel",
            options=[t["tunnel_id"] for t in tunnels],
            format_func=lambda x: tunnel_id_to_label.get(x, x),
            default=[],
            placeholder="All tunnels",
        )

    col4, col5 = st.columns(2)

    with col4:
        source_filter = st.multiselect(
            "Source",
            options=["Ontology", "Ingested (this session)"],
            default=[],
            placeholder="All sources",
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
# Overview map (driven by filters)
# -----------------------------------------------------------------------------
st.subheader("Geographic overview")

selected_tunnel_for_map = tunnel_filter[0] if len(tunnel_filter) == 1 else None
m = build_overview_map(
    filtered,
    selected_tunnel_id=selected_tunnel_for_map,
    height=420,
)
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

clicked_tooltip = map_state.get("last_object_clicked_tooltip") if map_state else None
if clicked_tooltip and clicked_tooltip in {d["defect_id"] for d in filtered}:
    st.session_state.selected_defect_id = clicked_tooltip
    st.info(
        f"Selected **{clicked_tooltip}** from the map — open the "
        f"**Defect Detail** page in the sidebar to view the FMEA chain."
    )

st.divider()

# -----------------------------------------------------------------------------
# Defect table — st.data_editor with controllable Select column
# -----------------------------------------------------------------------------
st.subheader("Defect list")

# Initialize selected_defects/selected_ids as empty so they always exist
selected_defects: list = []
selected_ids: list = []

if not filtered:
    st.info("No defects match the current filters.")
else:
    # ---- Select-all toggle (state owned by us, not the editor) ----
    select_all_key = (
        f"register_select_all_v{st.session_state.register_editor_version}"
    )
    if select_all_key not in st.session_state:
        st.session_state[select_all_key] = False

    select_all = st.checkbox(
        f"Select all {len(filtered)} visible",
        key=select_all_key,
        help="Tick to select every visible row for download or deletion. "
             "Untick to clear all selections.",
    )

    # ---- Build the editable dataframe with a leading Select column ----
    table_data = []
    for d in filtered:
        evidence = d.get("modality_evidence", {})
        modality_count = sum(
            1 for mod in ["RGB", "RGBD", "Thermal", "GPR"]
            if evidence.get(mod)
        )
        evidence_str = f"{modality_count}/4 modalities"

        cost = d.get("estimated_cost_aud", 0)
        cost_str = f"${cost:,}" if cost else "pending"

        source = "Ingested" if d.get("ingested") else "Ontology"
        tunnel_label = tunnel_id_to_label.get(d.get("tunnel_id"), "—")

        table_data.append({
            "Select": select_all,
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

    # The editor key embeds select_all so flipping the toggle remounts
    # the editor with the new default values; embeds the version so
    # post-deletion remounts work cleanly.
    editor_key = (
        f"register_editor_v{st.session_state.register_editor_version}_"
        f"{len(filtered)}_{select_all}"
    )

    edited_df = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        row_height=42,
        disabled=("ID", "Tunnel", "Description", "Location", "Type",
                  "Priority", "Evidence", "Source", "Est. cost"),
        column_config={
            "Select": st.column_config.CheckboxColumn(
                "Select",
                help="Tick to select this row for download or deletion",
                default=False,
                width="medium",
            ),
            "ID": st.column_config.TextColumn(width="small"),
            "Tunnel": st.column_config.TextColumn(width="medium"),
            "Location": st.column_config.TextColumn(width="medium"),
            "Priority": st.column_config.TextColumn(width="medium"),
            "Evidence": st.column_config.TextColumn(width="medium"),
            "Source": st.column_config.TextColumn(width="medium"),
            "Est. cost": st.column_config.TextColumn(width="medium"),
        },
        key=editor_key,
    )

    # Resolve the selection from the edited dataframe
    selected_mask = edited_df["Select"].fillna(False).astype(bool).tolist()
    selected_defects = [
        filtered[i] for i, picked in enumerate(selected_mask) if picked
    ]
    selected_ids = [d["defect_id"] for d in selected_defects]

    # If exactly one is selected, also feed it to the Defect Detail nav
    if len(selected_defects) == 1:
        st.session_state.selected_defect_id = selected_defects[0]["defect_id"]
        st.info(
            f"**1 selected** — `{selected_defects[0]['defect_id']}`. "
            f"Open **Defect Detail** in the sidebar for the FMEA chain, "
            f"or use the export buttons below."
        )
    elif len(selected_defects) > 1:
        st.info(
            f"**{len(selected_defects)} selected** "
            f"({', '.join(selected_ids[:5])}"
            f"{'…' if len(selected_ids) > 5 else ''}). "
            f"Selection is for actions like export. Defect Detail opens "
            f"only one defect at a time — pick a single row to navigate."
        )

# -----------------------------------------------------------------------------
# Export — selection-driven, with smart fallback
# -----------------------------------------------------------------------------
st.divider()

if filtered:
    if selected_defects:
        export_set = selected_defects
        export_label_csv = f"Download selected ({len(export_set)}) as CSV"
        export_label_json = f"Download selected ({len(export_set)}) as JSON"
        export_filename = "defect_register_selected"
    else:
        export_set = filtered
        export_label_csv = f"Download all filtered ({len(export_set)}) as CSV"
        export_label_json = f"Download all filtered ({len(export_set)}) as JSON"
        export_filename = "defect_register_filtered"

    col1, col2 = st.columns(2)
    with col1:
        csv = pd.DataFrame(export_set).to_csv(index=False).encode("utf-8")
        st.download_button(
            export_label_csv, csv,
            file_name=f"{export_filename}.csv",
            mime="text/csv",
        )
    with col2:
        jsonstr = json.dumps(export_set, indent=2, default=str).encode("utf-8")
        st.download_button(
            export_label_json, jsonstr,
            file_name=f"{export_filename}.json",
            mime="application/json",
        )

    st.caption(
        "Tip: tick rows in the table above to download a specific subset; "
        "with no selection, the buttons download every row that matches "
        "the current filters."
    )


# -----------------------------------------------------------------------------
# Subtle deletion — popover trigger + @st.dialog confirmation
# -----------------------------------------------------------------------------
@st.dialog("Confirm deletion")
def _confirm_delete_dialog(ids_to_delete: list, ontology_ids: list):
    """Modal confirmation for deletion."""
    st.markdown(
        f"You are about to delete **{len(ids_to_delete)} defect(s)**:"
    )
    st.code(", ".join(ids_to_delete), language=None)

    if ontology_ids:
        st.warning(
            f"⚠ {len(ontology_ids)} of these came from the ontology / "
            f"sample data. Deleting them only removes them from this "
            f"session — they will reappear after a server reboot, since "
            f"the JSON file itself is not modified."
        )

    final_confirm = st.checkbox(
        "I understand and want to proceed",
        key="delete_dialog_final_confirm",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Cancel", use_container_width=True,
                     key="delete_dialog_cancel"):
            st.rerun()
    with col_b:
        if st.button(
            "Delete", type="primary", use_container_width=True,
            disabled=not final_confirm,
            key="delete_dialog_proceed",
        ):
            ids_set = set(ids_to_delete)
            st.session_state.defects = [
                d for d in st.session_state.defects
                if d["defect_id"] not in ids_set
            ]
            st.session_state.ingested_defects = [
                d for d in st.session_state.get("ingested_defects", [])
                if d["defect_id"] not in ids_set
            ]
            if st.session_state.get("selected_defect_id") in ids_set:
                st.session_state.selected_defect_id = None
            # Bump version so the editor and select_all remount cleanly
            st.session_state.register_editor_version += 1
            st.rerun()


# Subtle trigger — at the very bottom of the page, only appears when
# something is actually selected. No decoration in the main flow.
if filtered and selected_defects:
    st.divider()
    with st.popover(
        f"⋯ Manage selection ({len(selected_defects)})",
        help="Subtle actions for the rows you've ticked in the table above.",
    ):
        st.caption(
            "These actions apply to the rows you've ticked above. Use "
            "deletion sparingly — the duplicate-prevention guard on the "
            "Ingest page already catches accidental double-submissions."
        )

        if st.button(
            f"🗑 Delete {len(selected_defects)} selected…",
            key="open_delete_dialog",
            help="Opens a confirmation dialog before anything is removed.",
        ):
            ontology_ids = [
                d["defect_id"] for d in selected_defects
                if not d.get("ingested")
            ]
            _confirm_delete_dialog(selected_ids, ontology_ids)
