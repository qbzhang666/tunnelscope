"""
PDF report generation — LaTeX, following the Tri-HB pattern
===========================================================

One click captures the whole session into a single document: KPIs,
the BIM 3-D model image, the full defect register, a case file per
defect (evidence, FMEA chain, prescribed intervention, cost build-up)
and the standards library the prescriptions cite.

Pipeline:  build LaTeX source  →  render the BIM image to PNG with
matplotlib (no browser needed)  →  compile with pdflatex/xelatex in a
temp dir (engine discovery and MiKTeX auto-install flags mirrored
from the Tri-HB app's report generator)  →  offer PDF + .tex + ZIP.

If no TeX distribution is found the .tex and figures are still
offered for compilation elsewhere.
"""

from __future__ import annotations

import io
import math
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from utils.bim3d import position_to_angle_deg, DEFAULT_DIAMETER_M
from utils.gis import PRIORITY_COLOURS
from utils.cost_model import estimate_defect_cost, effective_cost
from utils.library import list_library, dataset_summary

ONTOLOGY_URI = "http://w3id.org/tunnel-dt/ontology/v1.2"

# Survey-coverage demo rows (mirrors the Overview page)
COVERAGE_SECTIONS = [
    ("Section 1", "K248+500 - K249+200", 95),
    ("Section 2", "K249+200 - K249+900", 78),
    ("Section 3", "K249+900 - K250+600", 52),
    ("Section 4", "K250+600 - K251+300", 67),
]


# -----------------------------------------------------------------------------
# LaTeX text safety
# -----------------------------------------------------------------------------
_SPECIALS = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}
_UNICODE = {
    "²": r"\(^{2}\)", "³": r"\(^{3}\)", "°": r"\(^{\circ}\)",
    "Δ": r"\(\Delta\)", "±": r"\(\pm\)", "≥": r"\(\ge\)",
    "≤": r"\(\le\)", "·": r"\textperiodcentered{}", "×": r"\(\times\)",
    "—": "---", "–": "--", "’": "'", "‘": "`", "“": "``", "”": "''",
    "Ø": r"\O{}", "→": r"\(\rightarrow\)", "µ": r"\(\mu\)",
    "½": r"\(\tfrac{1}{2}\)", "✓": r"\checkmark{}",
}


def _esc(text: Any) -> str:
    """Escape arbitrary app text for LaTeX."""
    s = str(text if text is not None else "")
    s = "".join(_SPECIALS.get(ch, ch) for ch in s)
    s = "".join(_UNICODE.get(ch, ch) for ch in s)
    # drop anything else non-latin1 so pdflatex never chokes
    return s.encode("latin-1", "ignore").decode("latin-1")


# -----------------------------------------------------------------------------
# BIM model image — matplotlib 3-D (so no browser/kaleido is needed)
# -----------------------------------------------------------------------------
def render_bim_png(tunnel: Dict[str, Any],
                   bim_tunnel: Optional[Dict[str, Any]],
                   defects: List[Dict[str, Any]]) -> bytes:
    """Static render of the 3-D tunnel + defect markers for the report."""
    length = float(tunnel.get("length_m", 1000))
    diameter = float((bim_tunnel or {}).get("internal_diameter_m")
                     or DEFAULT_DIAMETER_M)
    r = diameter / 2.0

    fig = plt.figure(figsize=(11.0, 4.0), dpi=150)
    ax = fig.add_subplot(111, projection="3d")

    xs = np.linspace(0.0, length, 40)
    phi = np.linspace(0.0, 2 * np.pi, 36)
    X, P = np.meshgrid(xs, phi)
    ax.plot_surface(X, r * np.sin(P), r * np.cos(P),
                    alpha=0.12, color="#8A84C8", linewidth=0)

    plotted_any = False
    for priority in ("HIGH", "MEDIUM", "LOW"):
        pts = [d for d in defects
               if (d.get("priority") or "—") == priority
               and d.get("chainage_m")]
        if not pts:
            continue
        plotted_any = True
        ang = [math.radians(position_to_angle_deg(d.get("position", "")))
               for d in pts]
        ax.scatter(
            [min(float(d["chainage_m"]), length) for d in pts],
            [(r + 0.4) * math.sin(a) for a in ang],
            [(r + 0.4) * math.cos(a) for a in ang],
            color=PRIORITY_COLOURS.get(priority, "#999999"),
            s=42, depthshade=False, label=f"{priority} ({len(pts)})",
            edgecolors="white", linewidths=0.6,
        )

    ax.set_box_aspect((5, 1, 1))
    ax.set_xlabel("Chainage (m)", fontsize=9, labelpad=8)
    ax.set_yticks([])
    ax.set_zticks([])
    ax.tick_params(labelsize=8)
    ax.view_init(elev=18, azim=-62)
    if plotted_any:
        ax.legend(loc="upper right", fontsize=8, framealpha=0.7)
    ax.set_title(
        f"{tunnel.get('label', 'Tunnel')} — lining Ø{diameter:g} m, "
        f"{len([d for d in defects if d.get('chainage_m')])} defects "
        f"(length axis compressed)",
        fontsize=10,
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


# -----------------------------------------------------------------------------
# LaTeX source
# -----------------------------------------------------------------------------
def _kpis(defects: List[Dict[str, Any]]) -> Dict[str, Any]:
    active = [d for d in defects if d.get("status", "Active") == "Active"]
    high = [d for d in active if d.get("priority") == "HIGH"]
    ok = [d for d in active if d.get("completeness_score", 0) >= 0.75]
    total = sum(effective_cost(d)[0] for d in active)
    return {
        "active": len(active),
        "high": len(high),
        "confidence_pct": int(100 * len(ok) / len(active)) if active else 0,
        "total_cost": total,
    }


def _defect_case_file(d: Dict[str, Any]) -> str:
    """One defect's full case file as LaTeX."""
    est = estimate_defect_cost(d)
    parts = [
        f"\\subsection*{{{_esc(d.get('defect_id'))} --- "
        f"{_esc(d.get('description', ''))}}}",
        f"\\textbf{{Location:}} Ring {_esc(d.get('ring_id'))} "
        f"\\textperiodcentered{{}} K{float(d.get('chainage_m') or 0):.0f}m "
        f"\\textperiodcentered{{}} {_esc(d.get('position', '---'))} "
        f"\\hfill \\textbf{{Priority:}} {_esc(d.get('priority', '---'))} "
        f"\\textperiodcentered{{}} \\textbf{{Severity:}} "
        f"{_esc(d.get('severity', '---'))} "
        f"\\textperiodcentered{{}} \\textbf{{Evidence:}} "
        f"{int(d.get('completeness_score', 0) * 4)}/4\\par\\medskip",
    ]

    ev = d.get("modality_evidence") or {}
    if ev:
        rows = "".join(
            f"{_esc(mod)} & {_esc((e or {}).get('status', '---'))} & "
            f"{_esc((e or {}).get('finding') or '---')} \\\\\n"
            for mod, e in ev.items()
        )
        parts.append(
            "\\noindent\\textbf{Evidence by sensing source}\\par\n"
            "\\begin{tabular}{@{}lll@{}}\\toprule\n"
            "Source & Status & Finding \\\\ \\midrule\n"
            + rows + "\\bottomrule\\end{tabular}\\par\\medskip"
        )

    chain_bits = []
    for label, key in [("Failure mechanism", "failure_mechanism"),
                       ("Potential cause", "potential_cause"),
                       ("Threshold triggered", "threshold_triggered"),
                       ("Standard reference", "threshold_reference")]:
        if d.get(key):
            chain_bits.append(f"\\textbf{{{label}:}} {_esc(d[key])}")
    if chain_bits:
        parts.append("\\noindent " + "\\par\n\\noindent ".join(chain_bits)
                     + "\\par\\medskip")

    interventions = d.get("prescribed_interventions") or []
    if interventions:
        items = "".join(
            f"\\item {_esc(iv.get('step', ''))}"
            + (f" \\emph{{({_esc(iv.get('reference'))})}}"
               if iv.get("reference") else "")
            + "\n"
            for iv in interventions
        )
        parts.append("\\noindent\\textbf{Prescribed intervention}"
                     "\\begin{enumerate}\\itemsep2pt\n" + items
                     + "\\end{enumerate}")

    lines = "".join(
        f"{_esc(label)} & \\${amount:,.0f} \\\\\n"
        for label, amount in est["lines"]
    )
    recorded = (f"Engineer estimate \\${est['recorded']:,.0f} "
                + ("(inside model band)" if est["within_band"]
                   else "(outside model band --- review scope)")
                if est["recorded"] else "No engineer estimate --- "
                "modelled figure governs")
    parts.append(
        "\\noindent\\textbf{Cost build-up (unit-rate model)}\\par\n"
        f"\\emph{{{_esc(est['method'])}}}\\par\\smallskip\n"
        "\\begin{tabular}{@{}lr@{}}\\toprule\n"
        "Item & AUD \\\\ \\midrule\n" + lines +
        f"\\midrule \\textbf{{Expected}} & \\textbf{{\\${est['expected']:,.0f}}} \\\\\n"
        f"Band (\\(\\pm\\){est['band_pct'] * 100:.0f}\\%) & "
        f"\\${est['low']:,.0f} -- \\${est['high']:,.0f} \\\\\n"
        "\\bottomrule\\end{tabular}\\par\\smallskip\n"
        f"\\noindent {_esc(recorded)}\\par"
    )
    return "\n".join(parts)


def build_report_tex(tunnel: Dict[str, Any],
                     bim_tunnel: Optional[Dict[str, Any]],
                     defects: List[Dict[str, Any]],
                     bim_png_name: str,
                     include_case_files: bool = True) -> str:
    """Assemble the complete LaTeX source for the session report."""
    k = _kpis(defects)
    today = datetime.now().strftime("%d %B %Y")
    label = _esc(tunnel.get("label", "Tunnel"))

    sorted_defects = sorted(
        defects,
        key=lambda x: {"HIGH": 0, "MEDIUM": 1}.get(x.get("priority"), 2))

    # Section 4 — defect register (empty for a freshly set-up tunnel)
    if sorted_defects:
        register_rows = "".join(
            f"{_esc(d.get('defect_id'))} & {_esc(d.get('defect_type'))} & "
            f"{_esc(d.get('ring_id'))} & K{float(d.get('chainage_m') or 0):.0f}m & "
            f"{_esc(d.get('position', '---'))} & {_esc(d.get('priority', '---'))} & "
            f"{int(d.get('completeness_score', 0) * 4)}/4 & "
            f"\\${effective_cost(d)[0]:,.0f} ({effective_cost(d)[1]}) \\\\\n"
            for d in sorted_defects
        )
        register_block = (
            "\\begin{longtable}{@{}llllllll@{}}\\toprule\n"
            "ID & Type & Ring & Chainage & Position & Priority & Evidence & "
            "Est.\\ cost (basis) \\\\ \\midrule\n"
            f"{register_rows}\\bottomrule\n\\end{{longtable}}"
        )
    else:
        register_block = (
            "\\emph{No defects have been registered against this tunnel "
            "yet.} Log inspection findings on the Ingest page and they "
            "will appear here on the next report."
        )

    # Section 6 — survey coverage. The multimodal coverage figures are
    # demonstration data for Tunnel A only; do NOT print Tunnel A's
    # chainages under any other tunnel's report.
    if tunnel.get("tunnel_id") == "TUN-A" and sorted_defects:
        coverage_rows = "".join(
            f"{_esc(name)} & {_esc(span)} & {pct}\\% \\\\\n"
            for name, span, pct in COVERAGE_SECTIONS
        )
        coverage_block = (
            "Coverage = rings with evidence from \\(\\ge\\)3 of 4 sensing "
            "sources. Low-coverage sections are candidates for follow-up "
            "survey.\n\n\\medskip\n"
            "\\begin{tabular}{@{}lll@{}}\\toprule\n"
            "Section & Chainage range & Coverage \\\\ \\midrule\n"
            f"{coverage_rows}\\bottomrule\n\\end{{tabular}}"
        )
    else:
        coverage_block = (
            "\\emph{Multimodal survey-coverage statistics are "
            "demonstration data available for Tunnel A only; no coverage "
            "survey has been recorded for this tunnel.}"
        )

    bim_facts = (
        f"internal diameter {bim_tunnel.get('internal_diameter_m')} m, "
        f"lining {bim_tunnel.get('lining_thickness_m')} m, "
        f"{bim_tunnel.get('segments_per_ring')} segments/ring, "
        f"{_esc(bim_tunnel.get('joint_type', ''))}"
        if bim_tunnel else
        f"no BIM as-built record --- generic {DEFAULT_DIAMETER_M:g} m "
        f"lining assumed"
    )

    refs = "".join(
        f"\\item {_esc(e['label'])} --- \\emph{{{_esc(e['used_for'])}}} "
        f"(\\texttt{{{_esc(e['filename'])}}})\n"
        for e in list_library()
    )
    ds = dataset_summary()
    dataset_line = (
        f"\\item Inspection image dataset \\texttt{{BT\\_Monash-001}} --- "
        f"{ds['n_files']} files, {ds['size_mb']:.0f} MB (project folder "
        f"\\texttt{{2026 Ontology Paper}})\n"
        if ds.get("exists") else ""
    )

    if not include_case_files:
        case_files = ("\\emph{Per-defect case files were excluded from "
                      "this report.}")
    elif not sorted_defects:
        case_files = "\\emph{No defects to detail for this tunnel yet.}"
    else:
        case_files = "\n".join(_defect_case_file(d) for d in sorted_defects)

    return f"""\\documentclass[10pt,a4paper]{{article}}
\\usepackage[margin=2.2cm]{{geometry}}
\\usepackage{{booktabs,longtable,graphicx,amsmath,amssymb,xcolor}}
\\usepackage[hidelinks]{{hyperref}}
\\usepackage{{parskip}}
\\renewcommand{{\\familydefault}}{{\\sfdefault}}

\\title{{Tunnel Maintenance Digital Twin\\\\[2pt]
\\large Inspection \\& Intervention Report --- {label}}}
\\author{{Tunnel DT Dashboard (automated report)}}
\\date{{{today}}}

\\begin{{document}}
\\maketitle

\\section*{{1. Executive summary}}
\\begin{{tabular}}{{@{{}}llll@{{}}}}\\toprule
Open defects & Need action \\(\\le\\) 30 days & Diagnosis confidence &
12-month cost exposure \\\\ \\midrule
{k['active']} & {k['high']} & {k['confidence_pct']}\\% &
\\${k['total_cost']:,.0f} \\\\ \\bottomrule
\\end{{tabular}}

\\medskip
\\noindent\\textbf{{Bottom line:}} {k['high']} of {k['active']} open
defects need action within 30 days. Cost exposure blends
engineer-recorded estimates with the transparent unit-rate model
(basis marked per defect in Section~4).

\\section*{{2. How the figures are produced}}
\\textbf{{Pipeline:}} multimodal survey (RGB, depth, thermal, GPR)
\\(\\rightarrow\\) AI defect extraction \\(\\rightarrow\\) COBie asset
records \\(\\rightarrow\\) ontology knowledge base
(\\url{{{ONTOLOGY_URI}}}) \\(\\rightarrow\\) standards-based risk
ranking \\(\\rightarrow\\) costed work orders.

\\textbf{{Priority rule}} (AASHTO/Austroads coding): active water
(moisture GS/F) or spalling at the reinforcement (S-3/S-4)
\\(\\rightarrow\\) HIGH (act \\(\\le\\) 30 days); S-2 or damp (M)
\\(\\rightarrow\\) MEDIUM; otherwise LOW.

\\textbf{{Cost model:}}
\\(\\text{{expected}} = q \\times r \\times \\prod f_i +
\\text{{allowances}} + \\text{{mobilisation}}\\), with contingency band
\\(\\pm(12\\% + 30\\%\\,(1 - \\text{{completeness}}))\\). Rates are
indicative defaults to be calibrated against the maintenance contract.

\\section*{{3. Tunnel and BIM as-built}}
{label}: length {float(tunnel.get('length_m', 0)):,.0f} m,
{int(tunnel.get('rings_total') or 0):,} rings at
{tunnel.get('ring_length_m', 1.6)} m. BIM as-built: {bim_facts}.

\\begin{{center}}
\\includegraphics[width=\\textwidth]{{{bim_png_name}}}
\\end{{center}}

\\section*{{4. Defect register}}
{register_block}

\\section*{{5. Defect case files}}
{case_files}

\\section*{{6. Survey coverage by tunnel section}}
{coverage_block}

\\section*{{7. References and data}}
Standards and datasets bundled with the project
(folder \\texttt{{2026 Ontology Paper}}):
\\begin{{itemize}}\\itemsep2pt
{refs}{dataset_line}\\item Maintenance ontology:
\\url{{{ONTOLOGY_URI}}}
\\end{{itemize}}

\\vfill
\\noindent\\rule{{\\textwidth}}{{0.4pt}}\\\\
\\small Generated by the Tunnel DT dashboard. Demonstration data ---
anonymised tunnels; BIM and geological context are synthetic but
standards-consistent. Companion app to the paper
\\emph{{Serviceability-oriented Multimodal Data Integration for Tunnel
Maintenance Digital Twins in the Australian Context}}.
\\end{{document}}
"""


# -----------------------------------------------------------------------------
# LaTeX engine discovery + compilation (pattern from the Tri-HB app)
# -----------------------------------------------------------------------------
def _find_latex_engine(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    exe = name + (".exe" if os.name == "nt" else "")
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX"
        / "miktex" / "bin" / "x64" / exe,
        Path("C:/Program Files/MiKTeX/miktex/bin/x64") / exe,
        Path("C:/Program Files (x86)/MiKTeX/miktex/bin/x64") / exe,
        Path("/Library/TeX/texbin") / name,
        Path("/usr/bin") / name,
        Path("/usr/local/bin") / name,
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return None


def compile_latex_to_pdf(tex_source: str,
                         figures: List[Tuple[str, bytes]],
                         jobname: str) -> Tuple[Optional[bytes], str]:
    """Compile in a temp dir, two passes. Returns (pdf_bytes|None, msg)."""
    engine = next((e for e in (_find_latex_engine(n)
                               for n in ("pdflatex", "xelatex")) if e), None)
    if not engine:
        return None, (
            "No LaTeX engine (pdflatex/xelatex) found. Install MiKTeX or "
            "TeX Live, or download the .tex + figures below and compile "
            "elsewhere."
        )
    try:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            (tdp / f"{jobname}.tex").write_text(tex_source, encoding="utf-8")
            for fname, data in figures:
                (tdp / fname).write_bytes(data)
            cmd = [engine, "-interaction=nonstopmode"]
            if "miktex" in engine.lower():
                cmd += ["--enable-installer"]
            cmd += [f"{jobname}.tex"]
            for i in range(2):  # two passes for longtable/references
                try:
                    subprocess.run(cmd, cwd=td, capture_output=True,
                                   timeout=600 if i == 0 else 300)
                except subprocess.TimeoutExpired:
                    break
            out = tdp / f"{jobname}.pdf"
            if out.exists():
                return out.read_bytes(), ""
            log = tdp / f"{jobname}.log"
            if log.exists():
                text = log.read_text(encoding="utf-8", errors="replace")
                errs = [ln for ln in text.splitlines()
                        if ln.startswith("!") or "Fatal error" in ln]
                return None, "\n".join(errs[-20:]) or text[-1500:]
            return None, "LaTeX produced no PDF and no log."
    except Exception as exc:  # noqa: BLE001
        return None, f"LaTeX compilation failed: {type(exc).__name__}: {exc}"


# -----------------------------------------------------------------------------
# Orchestrator
# -----------------------------------------------------------------------------
def generate_report(tunnel: Dict[str, Any],
                    bim_tunnel: Optional[Dict[str, Any]],
                    defects: List[Dict[str, Any]],
                    include_case_files: bool = True) -> Dict[str, Any]:
    """Build tex + BIM figure, compile, and bundle a ZIP fallback."""
    png = render_bim_png(tunnel, bim_tunnel, defects)
    png_name = "bim_model.png"
    tex = build_report_tex(tunnel, bim_tunnel, defects, png_name,
                           include_case_files=include_case_files)
    jobname = f"{tunnel.get('tunnel_id', 'tunnel')}_report".replace("-", "_")
    pdf, message = compile_latex_to_pdf(tex, [(png_name, png)], jobname)

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{jobname}.tex", tex)
        z.writestr(png_name, png)
    return {
        "tex": tex,
        "png": png,
        "pdf": pdf,
        "message": message,
        "zip": zbuf.getvalue(),
        "jobname": jobname,
    }
