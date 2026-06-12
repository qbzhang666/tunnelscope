"""
Reference library — standards and datasets in '2026 Ontology Paper'
===================================================================

Maps the documents in the project's '2026 Ontology Paper' folder to
the app concepts they back, so pages (and the PDF report) can cite
and offer them. Paths are resolved at call time and missing files are
simply omitted — the app keeps working if the folder moves.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).parent.parent
LIBRARY_DIR = ROOT / "2026 Ontology Paper" / "2. Standards and Technical Specifications"
DATASET_DIR = ROOT / "2026 Ontology Paper" / "BT_Monash-001"

# (recursive glob pattern under LIBRARY_DIR, short label, what the app
# uses it for). Patterns rather than literal paths: the Google-Drive
# folder names contain lookalike unicode dashes that defeat exact
# matching, and globbing also survives future renames.
_REGISTRY = [
    ("**/Ch16 Tunnel Rehabilitation*.pdf",
     "AASHTO Ch16 — Tunnel Rehabilitation",
     "Defect thresholds, repair methods (FMEA chain, interventions, cost model)"),
    ("**/Ch15 Geotechnical*.pdf",
     "AASHTO Ch15 — Instrumentation",
     "Monitoring prescriptions (e.g. active-crack gauges)"),
    ("**/Appendix H*.pdf",
     "AASHTO Appendix H",
     "Supporting tunnel-manual material"),
    ("**/AGRT03*Operations_and_Maintenance.pdf",
     "Austroads AGRT03-24 — Operations & Maintenance",
     "Maintenance regimes, moisture coding, priority timeframes"),
    ("**/AGRT04*Retrofitting_Tunnels.pdf",
     "Austroads AGRT04-24 — Retrofitting Tunnels",
     "Rehabilitation method context"),
    ("**/AP-R673-22*Standard_V4.pdf",
     "Austroads RADS V4 (AP-R673-22)",
     "Asset data standard behind the RADS ontology"),
    ("**/Austroads_Data_Standard_v4_0_Measures.csv",
     "RADS V4 measures (CSV)",
     "Machine-readable RADS measures"),
    ("**/Austroads_Supporting_Table_Data.csv",
     "RADS supporting tables (CSV)",
     "Machine-readable RADS support data"),
    ("**/D1001_COBie*.pdf",
     "COBie Template Guide (D1001)",
     "COBie sheet structure used by the CV-to-COBie bridge"),
    ("**/COBie_RADS_Tunnel_Engineering_Example.xlsx",
     "COBie-RADS tunnel example (XLSX)",
     "Worked COBie example for tunnels"),
]


def list_library() -> List[Dict[str, Any]]:
    """Resolve the registry against disk. Only existing files returned."""
    out: List[Dict[str, Any]] = []
    if not LIBRARY_DIR.exists():
        return out
    for pattern, label, used_for in _REGISTRY:
        path = next(iter(sorted(LIBRARY_DIR.glob(pattern))), None)
        if path is None:
            continue
        # Google Drive cloud-only placeholders enumerate in globs but
        # fail stat() until hydrated — keep them listed; reading the
        # file (download button) triggers hydration.
        try:
            size_mb = path.stat().st_size / 1e6
        except OSError:
            size_mb = None
        out.append({
            "label": label,
            "used_for": used_for,
            "path": path,
            "filename": path.name,
            "size_mb": size_mb,
        })
    return out


def dataset_summary() -> Dict[str, Any]:
    """The BT_Monash-001 inspection dataset, summarised (not listed)."""
    if not DATASET_DIR.exists():
        return {"exists": False}
    files = [p for p in DATASET_DIR.rglob("*") if p.is_file()]
    return {
        "exists": True,
        "path": DATASET_DIR,
        "n_files": len(files),
        "size_mb": sum(p.stat().st_size for p in files) / 1e6,
    }
