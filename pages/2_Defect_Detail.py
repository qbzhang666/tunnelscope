"""
Defect Detail — page 2
======================

Shows the full FMEA reasoning chain for a single defect, including:
    - Three-state modality matrix (present / could enhance / not applicable)
    - Confidence tier label (HIGH / MEDIUM / LOW) — never blocks output
    - FMEA chain: Component → Mechanism → Defect → Indicator
                  → Cause → Threshold → Intervention
    - Prescribed intervention with materials, deadline, cost, standards ref
    - Modality enhancement recommendations
    - Work order generation and COBie export

REVISED:
- Selectbox moved to top of page (above title) to fix label cropping.
- Single-modality input is a first-class case — full intervention shown
  with a LOW confidence label rather than a refusal.
- Modality matrix has three states (present / could enhance / not applicable).

REVISED (Rev 8):
- BIM as-built context now embedded in the FMEA chain. A small
  "BIM ✓" badge appears next to the Component step; full as-built
  details (concrete mix, reinforcement, joint type, contractor,
  construction notes, repair history) live in an expandable section
  immediately under the Component row. The chain stays readable;
  the data is one click away.

REVISED (Rev 9):
- Geological context layer added alongside BIM. Inline "Geology" badge
  on the Component step (next to the BIM badge); expandable section
  immediately below the BIM expander showing the geological zone,
  layered stratigraphy, tunnel-substrate notes, hazards, and a
  per-defect graphical cross-section diagram.
- Cause caveat — short factual note about geological hazards at this
  defect's chainage rendered as a sidebar caveat next to (NOT inside)
  Step 5 (Cause) of the FMEA chain. Geology informs but does not
  modify the inferred cause.
"""

import streamlit as st
import json

from utils.ontology_loader import (
    load_ontology, load_defects, get_defect_by_id,
    get_fmea_chain, get_modality_evidence,
)
from utils.fmea_chain import (
    compute_completeness, recommend_missing_modality, confidence_tier,
    modality_state, MODALITY_LEVELS,
)
from utils.bim import get_bim_context
from utils.geology import (
    get_geology_context, build_cross_section_svg,
    get_geology_cause_caveat,
)
from utils.styling import apply_custom_css

st.set_page_config(page_title="Defect Detail", layout="wide")
apply_custom_css()

if "graph" not in st.session_state:
    st.session_state.graph = load_ontology()
    st.session_state.defects = load_defects(st.session_state.graph)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _summarise_measurements(defect: dict) -> str:
    """Build a one-line summary of any quantitative measurements on file."""
    m = defect.get("measurements", {})
    parts = []
    if m.get("crack_width_mm"):
        parts.append(f"width {m['crack_width_mm']} mm")
    if m.get("spall_depth_mm"):
        parts.append(f"depth {m['spall_depth_mm']} mm")
    if m.get("area_cm2"):
        parts.append(f"area {m['area_cm2']} cm²")
    if not parts:
        return "Quantitative measurements not yet recorded."
    return "; ".join(parts)


def _default_interventions_for_type(defect_type: str) -> list:
    """
    Fall-back intervention plan keyed on defect type, used when the
    ontology has no explicit prescribed_interventions for the record.
    """
    table = {
        "Cracks": [
            {"step": "Install crack monitoring gauges to determine "
                     "active vs dormant status (minimum 2 readings, "
                     "30 days apart)",
             "rationale": "Active cracks must not be rigidly rebonded.",
             "reference": "AASHTO Ch16 §16.7"},
            {"step": "If dormant: epoxy resin injection per "
                     "AS 3600 / amine-based resin for moist substrate",
             "rationale": "Restores monolithic concrete integrity.",
             "reference": "AASHTO Ch16 Table 16-2"},
            {"step": "If active: investigate root cause; seal with "
                     "flexible chemical grout if leaking",
             "rationale": "Rigid repair will fail if movement continues.",
             "reference": "AASHTO Ch16 §16.7.3"},
        ],
        "Spalls": [
            {"step": "Remove loose and unsound concrete by "
                     "hydro-demolition or controlled chipping",
             "rationale": "Sound substrate is required for repair adhesion.",
             "reference": "AASHTO Ch16 §16.6.2"},
            {"step": "Inspect exposed reinforcement; clean to SA 2½ "
                     "if section loss < 30%, replace if ≥ 30%",
             "rationale": "Threshold for structural-engineer review.",
             "reference": "AASHTO Ch16 Table 16-3"},
            {"step": "Reinstate with polymer-modified mortar or "
                     "shotcrete; cure per manufacturer specification",
             "rationale": "Restores cover and protects rebar.",
             "reference": "AS 5100.5 / AASHTO Ch16"},
        ],
        "LeakingJoints": [
            {"step": "Categorise leakage per Austroads coding "
                     "(M / PM / GS / F / D)",
             "rationale": "Drives grout selection.",
             "reference": "Austroads Guide Part 5"},
            {"step": "Inject hydrophilic polyurethane grout for "
                     "active flow; epoxy for damp-only",
             "rationale": "Hydrophilic PU expands on contact with water.",
             "reference": "AASHTO Ch16 Table 16-2"},
            {"step": "Re-inspect at 30 days; re-treat if leakage recurs",
             "rationale": "Confirms seal integrity.",
             "reference": "Austroads Guide Part 5"},
        ],
        "Efflorescence": [
            {"step": "Mechanically remove deposits by wire brushing "
                     "or low-pressure water blasting",
             "rationale": "Restores surface aesthetics and exposes "
                          "underlying substrate for inspection.",
             "reference": "AASHTO Ch16 §16.5"},
            {"step": "Investigate moisture pathway (likely cause); "
                     "seal upstream source if identified",
             "rationale": "Without sealing, deposits will recur.",
             "reference": "AASHTO Ch16 §16.7"},
        ],
        "RebarCorrosion": [
            {"step": "Quantify section loss by callipers or ultrasonic "
                     "thickness gauge",
             "rationale": "Threshold of 30% triggers structural review.",
             "reference": "AASHTO Ch16 Table 16-3"},
            {"step": "Remove unsound concrete, abrasive-blast rebar "
                     "to SA 2½, apply zinc-rich primer within 4 hours",
             "rationale": "Prevents flash-rust before reinstatement.",
             "reference": "AS/NZS 2312"},
            {"step": "Reinstate cover with polymer-modified mortar; "
                     "consider impressed-current cathodic protection "
                     "for chloride-contaminated environments",
             "rationale": "Long-term mitigation in saline conditions.",
             "reference": "ISO 12696"},
        ],
        "Delamination": [
            {"step": "Acoustic sounding (chain-drag or hammer) to map "
                     "extent of delaminated zones",
             "rationale": "Visual extent typically underestimates "
                          "subsurface extent.",
             "reference": "AASHTO Ch16 §16.6"},
            {"step": "Remove all delaminated material; reinstate per "
                     "Spalls protocol",
             "rationale": "Standard repair sequence.",
             "reference": "AASHTO Ch16 §16.6.2"},
        ],
    }
    if defect_type in table:
        return table[defect_type]
    return [
        {"step": "Engineer-led inspection to confirm defect "
                 "classification and select intervention",
         "rationale": "Defect type does not match a standard protocol "
                      "in the loaded knowledge base.",
         "reference": "Engineer judgement"},
    ]


# -----------------------------------------------------------------------------
# Page header — title FIRST, then selectbox below with breathing room
# -----------------------------------------------------------------------------
st.title("Defect detail")
st.caption(
    "Full FMEA reasoning chain and prescribed intervention for a single "
    "defect. Pick a defect from the dropdown below."
)

defects = st.session_state.defects
defect_ids = [d["defect_id"] for d in defects]

if not defect_ids:
    st.warning(
        "No defects available. Use the **Ingest** page to register one, "
        "or load sample data into the ontology."
    )
    st.stop()

default_id = st.session_state.get("selected_defect_id") or defect_ids[0]

# Add visual breathing room before the selectbox so the label can't be
# clipped by content above (the bug we hit on the first revision).
st.write("")

selected_id = st.selectbox(
    "Select defect",
    options=defect_ids,
    index=defect_ids.index(default_id) if default_id in defect_ids else 0,
    key="defect_detail_selector",
)

defect = next((d for d in defects if d["defect_id"] == selected_id), {})
if not defect:
    st.error(f"Defect {selected_id} not found.")
    st.stop()

st.divider()

# -----------------------------------------------------------------------------
# Header for the selected defect
# -----------------------------------------------------------------------------
st.subheader(f"{defect['defect_id']} — {defect['description']}")
caption_parts = [
    f"Ring {defect['ring_id']}",
    f"Chainage K{defect.get('chainage_m', 0):.0f}m",
    f"{defect.get('position', '—')}",
    f"Discovered {defect.get('discovered_on', 'unknown')}",
]
if defect.get("ingested"):
    caption_parts.append(
        f"📤 ingested from `{defect.get('source_filename', 'upload')}`"
    )
st.caption(" · ".join(caption_parts))

# Compute confidence tier upfront — used in header and throughout
evidence = defect.get("modality_evidence", {})
available_modalities = [m for m in ["RGB", "RGBD", "Thermal", "GPR"]
                        if evidence.get(m)]
score, covered, missing = compute_completeness(
    defect["defect_type"], available_modalities
)
tier = confidence_tier(score)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Defect type", defect["defect_type"])
with col2:
    st.metric("Priority", defect.get("priority", "—"))
with col3:
    st.metric("Confidence", tier["label"])
with col4:
    cost = defect.get("estimated_cost_aud", 0)
    st.metric("Est. cost", f"${cost:,}" if cost else "Pending")

if tier["tier"] == "HIGH":
    st.success(f"**{tier['label']}** — {tier['action']}")
elif tier["tier"] == "MEDIUM":
    st.info(f"**{tier['label']}** — {tier['action']}")
else:
    st.warning(f"**{tier['label']}** — {tier['action']}")

st.divider()

# -----------------------------------------------------------------------------
# Modality evidence matrix — three states
# -----------------------------------------------------------------------------
st.subheader("Evidence sources")
st.caption(
    "What each sensing modality contributes for this defect. "
    "Green = present · Grey = could enhance · Disabled = not applicable to "
    "this defect type."
)

cols = st.columns(4)
for i, modality in enumerate(["RGB", "RGBD", "Thermal", "GPR"]):
    with cols[i]:
        mod_data = evidence.get(modality, {})
        has_evidence = bool(mod_data)
        state = modality_state(modality, defect["defect_type"], has_evidence)

        st.markdown(f"**{modality}**")

        if state == "present":
            status = "✓ " + mod_data.get("status", "Confirmed")
            st.success(status)
            if mod_data.get("finding"):
                st.caption(mod_data["finding"])
            if mod_data.get("fmea_level"):
                st.caption(f"Level: {mod_data['fmea_level']}")

        elif state == "could_enhance":
            st.markdown(":grey[○ Not collected]")
            st.caption("Optional — would add evidence at the "
                       f"{MODALITY_LEVELS.get(modality, ['—'])[0]} level.")

        else:  # not_applicable
            st.markdown(":grey[— Not applicable]")
            st.caption("This modality cannot detect this defect type.")

if evidence.get("InspectionReport") or evidence.get("RGB", {}).get("status") == "Reported by inspector":
    st.markdown("---")
    rep = evidence.get("InspectionReport") or evidence.get("RGB", {})
    st.markdown("**📄 Inspection report** — " + rep.get("status", "Recorded"))
    if rep.get("finding"):
        st.caption(rep["finding"])

# -----------------------------------------------------------------------------
# Evidence breadth & enhancement suggestions
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Evidence breadth")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**FMEA levels covered**")
    if covered:
        for level in covered:
            st.markdown(f"✓ {level.replace('_', ' ')}")
    else:
        st.markdown(":grey[None — relying on a single source.]")
    if missing:
        st.markdown("**Levels not yet covered**")
        for level in missing:
            st.markdown(f":grey[○ {level.replace('_', ' ')}]")

with col2:
    st.markdown(f"**Confidence tier:** {tier['label']}")
    st.caption(tier["upgrade"])

    recommendations = recommend_missing_modality(
        defect["defect_type"], available_modalities
    )
    if recommendations:
        st.markdown("**Recommended enhancements**")
        for rec in recommendations[:3]:
            st.markdown(f"- Deploy **{rec['modality']}** — {rec['rationale']}")
    else:
        st.markdown(":green[No further surveys needed for this decision.]")

# -----------------------------------------------------------------------------
# FMEA reasoning chain
# -----------------------------------------------------------------------------
st.divider()
st.subheader("FMEA reasoning chain")

# Resolve BIM context once. Drives both the inline badge on the Component
# step and the expandable as-built section.
bim_context = get_bim_context(defect)
bim_segment = bim_context["segment"]
bim_tunnel = bim_context["tunnel"]
bim_repairs = bim_context["repairs"]

# Resolve geological context once. Drives the geology badge alongside
# BIM, the geology expandable section, and the cause-step caveat.
geo_context = get_geology_context(defect)
geo_zone = geo_context["zone"]
geo_strat = geo_context["stratigraphy"]
geo_tunnel = geo_context["tunnel"]

chain_data = defect.get("fmea_chain", [])
if not chain_data:
    # Build the Component step's value so it includes segment-aware text
    component_value = f"Concrete lining at Ring {defect['ring_id']}"
    if bim_segment:
        component_value += (
            f" — within construction segment "
            f"**{bim_segment['segment_id']}** "
            f"({bim_segment.get('name', '—')})"
        )

    chain_data = [
        {"step": "1. Component",
         "value": component_value,
         "source": f"COBie.Component.ComponentName = \"Ring_{defect['ring_id']}\""},
        {"step": "2. Failure mechanism",
         "value": defect.get("failure_mechanism", "Not classified"),
         "source": "tun:hasMechanism"},
        {"step": "3. Defect condition",
         "value": defect.get("description", ""),
         "source": f"tun:DefectCondition tun:{defect['defect_type']}"},
        {"step": "4. Indicators",
         "value": defect.get("indicators_summary",
                             _summarise_measurements(defect)),
         "source": "tun:hasIndicator"},
        {"step": "5. Potential cause",
         "value": defect.get("potential_cause", "Inferred from defect type"),
         "source": "tun:hasPotentialCause"},
        {"step": "6. Threshold triggered",
         "value": defect.get("threshold_triggered",
                             "AASHTO Ch16 standard threshold"),
         "source": defect.get("threshold_reference",
                              "AASHTO Manual for Bridge Element Inspection")},
    ]


def _render_bim_inline_badge():
    """A small inline badge after the Component step's value text."""
    if bim_segment is not None:
        st.caption(
            f"🧱 **BIM ✓** — as-built record found for segment "
            f"`{bim_segment['segment_id']}`. See **As-built details** "
            f"below for concrete mix, reinforcement, contractor, "
            f"construction notes, and repair history."
        )
    elif bim_tunnel is not None:
        # Tunnel known, but the ring is out of segment range
        st.caption(
            f"🧱 **BIM ⚠** — tunnel record found, but Ring "
            f"{defect.get('ring_id', '?')} is outside the defined "
            f"segment ranges. Check the ring number is correct."
        )
    else:
        # No tunnel_id on the defect (legacy) or tunnel not in BIM file
        st.caption(
            f"🧱 **BIM —** — no as-built record linked to this defect. "
            f"Defect predates the BIM extension or has no tunnel_id."
        )


def _render_bim_expandable():
    """
    The full as-built section. Renders ONLY when there's a segment to
    show, immediately after the Component row. Skipped silently when
    no segment matches — the inline badge already explains why.
    """
    if bim_segment is None or bim_tunnel is None:
        return

    expander_label = (
        f"📋 As-built details — segment {bim_segment['segment_id']} "
        f"({bim_segment.get('name', '—')})"
    )
    with st.expander(expander_label, expanded=False):
        if bim_context.get("is_demo_data"):
            st.caption(
                "⚠ Demonstration data — not contractor or owner records. "
                "Synthetic attributes consistent with published "
                "precast-segmental-tunnel construction practice "
                "(ITA WG2, AFTES, fib) and the construction era of the "
                "real tunnel this is anonymised from."
            )

        # ---- Construction summary ----
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Construction**")
            st.markdown(
                f"- Type: {bim_segment.get('construction_type', '—')}\n"
                f"- Started: {bim_segment.get('construction_dates', {}).get('start', '—')}\n"
                f"- Completed: {bim_segment.get('construction_dates', {}).get('completed', '—')}\n"
                f"- Contractor: {bim_segment.get('contractor', '—')}\n"
                f"- Ring range: {bim_segment.get('ring_range', ['?', '?'])[0]}"
                f" – {bim_segment.get('ring_range', ['?', '?'])[1]}\n"
                f"- Chainage range: K{bim_segment.get('chainage_range_m', [0, 0])[0]:.0f}m"
                f" – K{bim_segment.get('chainage_range_m', [0, 0])[1]:.0f}m"
            )
        with col_b:
            st.markdown("**Tunnel-level**")
            st.markdown(
                f"- Internal diameter: {bim_tunnel.get('internal_diameter_m', '—')} m\n"
                f"- Lining thickness: {bim_tunnel.get('lining_thickness_m', '—')} m\n"
                f"- Segments per ring: {bim_tunnel.get('segments_per_ring', '—')}\n"
                f"- Ring length: {bim_tunnel.get('ring_length_m', '—')} m\n"
                f"- Joint type: {bim_tunnel.get('joint_type', '—')}\n"
                f"- Lining type: {bim_tunnel.get('lining_type', '—')}"
            )

        # ---- Concrete mix ----
        st.markdown("**Concrete mix design**")
        mix = bim_segment.get("concrete_mix", {})
        if mix:
            additives = mix.get("additives", [])
            additives_str = "; ".join(additives) if additives else "—"
            st.markdown(
                f"- Designation: **{mix.get('designation', '—')}** "
                f"({mix.get('compressive_strength_mpa', '—')} MPa)\n"
                f"- Cement: {mix.get('cement_type', '—')}\n"
                f"- W/C ratio: {mix.get('water_cement_ratio', '—')}\n"
                f"- Aggregate max size: {mix.get('aggregate_max_size_mm', '—')} mm\n"
                f"- Additives: {additives_str}\n"
                f"- Exposure class: {mix.get('exposure_class', '—')}\n"
                f"- Cover to reinforcement: "
                f"{mix.get('cover_to_reinforcement_mm', '—')} mm"
            )
        else:
            st.markdown(":grey[No mix design record.]")

        # ---- Reinforcement ----
        st.markdown("**Reinforcement**")
        reo = bim_segment.get("reinforcement", {})
        if reo:
            fibre_line = (
                f"- Steel fibres: {reo.get('fibre_dosage_kg_m3', '—')} kg/m³"
                if reo.get("fibre_reinforced") else "- Steel fibres: none"
            )
            st.markdown(
                f"- Primary: {reo.get('primary', '—')}\n"
                f"- Secondary: {reo.get('secondary', '—')}\n"
                f"{fibre_line}\n"
                f"- Epoxy-coated: "
                f"{'yes' if reo.get('epoxy_coated') else 'no'}"
            )
        else:
            st.markdown(":grey[No reinforcement record.]")

        # ---- Construction notes ----
        notes = bim_segment.get("construction_notes")
        if notes:
            st.markdown("**Construction notes**")
            st.info(notes)

        # ---- Design standards & repair history ----
        st.markdown("**Design standards (era)**")
        standards = bim_tunnel.get("design_standards", [])
        if standards:
            st.markdown(
                "\n".join(f"- {s}" for s in standards)
            )

        if bim_repairs:
            st.markdown(f"**Repair history near Ring {defect['ring_id']}** "
                        f"(within ±5 rings)")
            for rep in bim_repairs:
                st.markdown(
                    f"- **Ring {rep.get('ring_id', '?')}** · "
                    f"{rep.get('date', '?')} · "
                    f"{rep.get('defect_type', '?')} → "
                    f"{rep.get('intervention', '?')}"
                )
                if rep.get("outcome"):
                    st.caption(f"  Outcome: {rep['outcome']}")
        else:
            st.markdown(
                f":grey[No repair history recorded within ±5 rings of "
                f"Ring {defect.get('ring_id', '?')}.]"
            )


def _render_geo_inline_badge():
    """A small inline badge after the BIM badge on the Component step.

    Three states: ✓ (zone found), ⚠ (tunnel known but chainage out of
    range), — (no tunnel_id at all).
    """
    if geo_zone is not None:
        st.caption(
            f"🗺️ **Geology ✓** — geological zone identified: "
            f"`{geo_zone['zone_id']}` "
            f"({geo_zone.get('name', '—')}). "
            f"See **Geological context** below for stratigraphy, "
            f"hazards, and a cross-section diagram at this chainage."
        )
    elif geo_tunnel is not None:
        st.caption(
            f"🗺️ **Geology ⚠** — tunnel record found, but chainage "
            f"K{defect.get('chainage_m', 0):.0f}m is outside the defined "
            f"geological zones. Check the chainage value."
        )
    else:
        st.caption(
            "🗺️ **Geology —** — no geological context linked to this "
            "defect. Defect has no tunnel_id."
        )


def _render_geo_expandable():
    """
    The full geological context section. Renders only when there's a
    zone to show, immediately after the BIM expander on the Component
    step.

    Three subsections:
      1. Zone-along-chainage description (which zone this is, what
         the substrate is, water table, hazards).
      2. Stratigraphy at the nearest sample (layered table).
      3. Cross-section diagram (matplotlib SVG embedded inline).
    """
    if geo_zone is None or geo_tunnel is None:
        return

    expander_label = (
        f"🗺️ Geological context — zone {geo_zone['zone_id']} "
        f"({geo_zone.get('name', '—')})"
    )
    with st.expander(expander_label, expanded=False):
        if geo_context.get("is_demo_data"):
            st.caption(
                "⚠ Demonstration data — synthetic geological context. "
                "Tunnel B (anonymised Burnley) data is well-grounded "
                "in published sources (Paul et al. 2014, "
                "Holdgate/Cupper 2003, Lamb & Hutchinson 1998). "
                "Tunnel A geology is plausible per Melbourne regional "
                "mapping but stratigraphic boundaries are interpolated."
            )

        # ---- Zone summary ----
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Zone**")
            chainage_lo, chainage_hi = geo_zone.get("chainage_range_m",
                                                    [0, 0])
            st.markdown(
                f"- ID: `{geo_zone['zone_id']}`\n"
                f"- Range: K{chainage_lo:.0f}m – K{chainage_hi:.0f}m\n"
                f"- Primary unit: {geo_zone.get('primary_unit', '—')}\n"
                f"- Tunnel substrate: {geo_zone.get('tunnel_substrate', '—')}"
            )
        with col_b:
            st.markdown("**Hydrogeology (preview — Rev 10 will expand this)**")
            st.markdown(
                f"- Water table depth: "
                f"{geo_zone.get('groundwater_depth_to_water_table_m', '—')} m\n"
                f"- Tunnel depth below ground: "
                f"{geo_zone.get('tunnel_depth_below_ground_m', '—')} m\n"
                f"- Tunnel below water table: "
                f"{geo_zone.get('tunnel_depth_below_water_table_m', '—')} m"
            )

        # ---- Engineering notes ----
        notes = geo_zone.get("engineering_notes")
        if notes:
            st.markdown("**Engineering notes for this zone**")
            st.info(notes)

        # ---- Hazards ----
        hazards = geo_zone.get("hazards", [])
        if hazards:
            st.markdown("**Documented geological hazards in this zone**")
            for h in hazards:
                st.markdown(f"- {h}")

        # ---- Stratigraphy table (text) ----
        if geo_strat:
            st.markdown(
                f"**Layered stratigraphy** "
                f"(sample at K{geo_strat.get('sample_chainage_m', '?')}m, "
                f"defect at K{defect.get('chainage_m', 0):.0f}m)"
            )
            for layer in geo_strat.get("layers", []):
                top = layer.get("top_depth_m", 0)
                bottom = layer.get("bottom_depth_m", 0)
                unit = layer.get("unit", "—")
                st.markdown(
                    f"- {top:.1f}–{bottom:.1f} m: **{unit}**"
                )

            # ---- Cross-section diagram ----
            st.markdown("**Cross-section diagram**")
            try:
                svg = build_cross_section_svg(
                    geo_strat,
                    defect_chainage_m=defect.get("chainage_m", 0),
                    defect_position=defect.get("position"),
                )
                if svg:
                    # SVG is text/XML, not a raster format — st.image()
                    # uses Pillow which can't decode SVG. Embed it as
                    # inline HTML instead, which keeps the SVG scalable
                    # and lets matplotlib's vector output render crisp
                    # at any zoom level.
                    st.markdown(
                        f'<div style="max-width: 760px; margin: 0 auto;">'
                        f'{svg}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            except Exception as exc:
                st.caption(
                    f":grey[Could not render cross-section: {exc}]"
                )

        # ---- Provenance ----
        provenance = geo_tunnel.get("data_provenance")
        if provenance:
            st.caption(f"**Data provenance:** {provenance}")


# Render the chain. After the Component row (step 1), inject the
# inline badges and the expandable BIM and geology sections. After
# the Cause row (step 5), inject a sidebar caveat with the geological
# hazards at this chainage.
for step in chain_data:
    with st.container():
        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown(f"**{step['step']}**")
        with col2:
            st.write(step["value"])
            if step.get("source"):
                st.code(step["source"], language=None)
            # Inline BIM badge attached to Component step
            if step["step"].startswith("1.") or "Component" in step["step"]:
                _render_bim_inline_badge()
                _render_geo_inline_badge()
            # Geology cause caveat — small sidebar note next to Cause
            if step["step"].startswith("5.") or "cause" in step["step"].lower():
                caveat = get_geology_cause_caveat(defect)
                if caveat:
                    with st.container(border=True):
                        st.caption(
                            "Geological context (informational — does NOT "
                            "modify the inferred cause above)"
                        )
                        st.markdown(caveat)

    # Expandable BIM section directly after Component row
    if step["step"].startswith("1.") or "Component" in step["step"]:
        _render_bim_expandable()
        _render_geo_expandable()

# -----------------------------------------------------------------------------
# Prescribed intervention — ALWAYS shown
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Prescribed intervention")

if tier["tier"] == "LOW":
    st.caption(
        "ℹ️ Recommendation generated from limited evidence. Treat as an "
        "engineer-review starting point. Consider deploying additional "
        "modalities before committing to scheduling."
    )

interventions = defect.get("prescribed_interventions", [])
if not interventions:
    interventions = _default_interventions_for_type(defect["defect_type"])

for i, iv in enumerate(interventions, 1):
    with st.container():
        col1, col2 = st.columns([1, 6])
        with col1:
            st.markdown(f"### {i}")
        with col2:
            st.markdown(f"**{iv['step']}**")
            if iv.get("rationale"):
                st.caption(iv["rationale"])
            if iv.get("reference"):
                st.code(iv["reference"], language=None)

deadline = defect.get("deadline_days")
if deadline:
    st.warning(f"Complete within **{deadline} days** of approval.")

# -----------------------------------------------------------------------------
# Actions
# -----------------------------------------------------------------------------
st.divider()
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("Generate work order", type="primary"):
        st.success("Work order generated. See download below.")
        work_order = {
            "work_order_id": f"WO-{defect['defect_id']}-{defect.get('discovered_on', '')}",
            "defect": defect,
            "confidence_tier": tier,
            "evidence_breadth": {
                "score": score,
                "modalities_present": available_modalities,
                "modalities_missing": [
                    m for m in ["RGB", "RGBD", "Thermal", "GPR"]
                    if m not in available_modalities
                ],
            },
            "approval_status": "PENDING_ENGINEER_REVIEW",
        }
        st.download_button(
            "Download work order (JSON)",
            json.dumps(work_order, indent=2, default=str).encode("utf-8"),
            file_name=f"work_order_{defect['defect_id']}.json",
            mime="application/json",
        )
with col2:
    if st.button("Export COBie rows"):
        st.info("Exporting COBie rows for this defect...")
with col3:
    if st.button("Request additional survey"):
        if recommendations:
            top = recommendations[0]
            st.info(f"Survey request queued: deploy **{top['modality']}**.")
        else:
            st.info("No further surveys recommended.")
