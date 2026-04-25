<div align="center">

# 🛣️ Tunnel Digital Twin — Operator Dashboard

### *Serviceability-Oriented Multimodal Maintenance for Australian Road Tunnels*

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://amandahuang-336-tunnel-dt2026-app-zmguxo.streamlit.app/)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.39+-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![rdflib](https://img.shields.io/badge/rdflib-7.0+-orange.svg)](https://rdflib.readthedocs.io/)

*A human-facing dashboard that queries an OWL ontology of tunnel defects, FMEA chains, and prescribed interventions — the operator-facing layer of a serviceability-oriented digital twin.*

[**🚀 Live demo**](https://amandahuang-336-tunnel-dt2026-app-zmguxo.streamlit.app/) · [**📖 Paper context**](#-paper-context) · [**⚡ Quickstart**](#-quickstart) · [**🐛 Report a bug**](https://github.com/amandahuang-336/tunnel-dt2026/issues)

</div>

---

## ✨ What this is

This dashboard accompanies the paper:

> **Serviceability-oriented Multimodal Data Integration for Tunnel Maintenance Digital Twins in the Australian Context.**

It demonstrates how a populated OWL ontology — authored in Protégé and queried through `rdflib` — can drive an operator-facing maintenance interface. Each defect carries its full FMEA reasoning chain, modality evidence, prescribed interventions, and traceable references to Australian standards.

> 💡 **Think of it as the human face of the digital twin.** Protégé authors the schema; this app queries it for end users.

---

## 🏗️ Architecture

```
   ┌──────────────────┐
   │   Protégé        │    ← Ontology authoring (TBox)
   │   (desktop)      │
   └────────┬─────────┘
            │ Export Turtle/OWL
            ▼
   ┌──────────────────┐
   │ tunnel_maint     │    ← Schema layer (classes, properties, axioms)
   │  enance.ttl      │
   └────────┬─────────┘
            │ rdflib loads into memory
            ▼
   ┌──────────────────┐
   │  This Streamlit  │    ← Operator interface (this repo)
   │  app             │
   └────────┬─────────┘
            │
            ├─→ 📊 Defect Register
            ├─→ 🔍 Defect Detail (FMEA chain)
            ├─→ 💻 SPARQL Console
            ├─→ 🔄 CV → COBie Bridge
            └─→ 🧠 Ontology Browser
```

---

## ⚡ Quickstart

### 🟢 Option 1 — Try it online (no install needed)

👉 [**Open the live app**](https://amandahuang-336-tunnel-dt2026-app-zmguxo.streamlit.app/)

Hosted on Streamlit Community Cloud. No setup required — just click and explore.

### 🔵 Option 2 — Run it locally

```bash
# 1️⃣  Clone the repository
git clone https://github.com/amandahuang-336/tunnel-dt2026.git
cd tunnel-dt2026

# 2️⃣  Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows PowerShell

# 3️⃣  Install dependencies
pip install -r requirements.txt

# 4️⃣  Launch the dashboard
streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

> ⚠️ **Common pitfall:** The terminal must stay open while the app runs. Closing it stops the server.

> 💡 **`streamlit: command not found`?** Use `python -m streamlit run app.py` instead.

---

## 🗂️ Project Structure

```
tunnel-dt2026/
│
├── 📄 app.py                          # Main entry — overview dashboard
├── 📄 requirements.txt                # Python dependencies (pinned)
├── 📄 README.md                       # This file
├── 📄 LICENSE                         # MIT licence
│
├── 📁 .streamlit/
│   ├── config.toml                    # Theme + headless server config
│   └── credentials.toml               # Bypass first-run email prompt
│
├── 📁 pages/                          # 🎯 Multipage Streamlit pages
│   ├── 1_Defect_Register.py           # Ranked filterable list
│   ├── 2_Defect_Detail.py             # Full FMEA chain for one defect
│   ├── 3_SPARQL_Console.py            # Direct query interface
│   ├── 4_CV_to_COBie_Bridge.py        # Defect semantic extraction demo
│   └── 5_Ontology_Browser.py          # Class hierarchy + properties
│
├── 📁 utils/                          # 🔧 Shared backend modules
│   ├── ontology_loader.py             # Load + cache the ontology
│   ├── sparql_queries.py              # Pre-built SPARQL queries
│   ├── fmea_chain.py                  # Chain traversal + completeness
│   ├── cv_to_cobie.py                 # CV output → COBie row conversion
│   └── styling.py                     # Custom CSS theming
│
├── 📁 ontology/                       # 📚 TBox (schema) files
│   ├── tunnel_maintenance.ttl         # Main domain ontology
│   ├── cobie_ontology.ttl             # COBie integration layer
│   └── austroads_rads.ttl             # Australian RADS layer
│
├── 📁 data/                           # 🧪 ABox (instance) data
│   ├── defects_tunnel_a.json          # 7 worked defect examples
│   ├── cv_detections_sample.json      # Example CV pipeline output
│   └── cobie_rows_sample.csv          # Example COBie spreadsheet rows
│
├── 📁 queries/                        # 💾 Reusable SPARQL queries
│   ├── all_defects_by_ring.rq
│   ├── completeness_score.rq
│   ├── high_priority_defects.rq
│   ├── fmea_chain_for_defect.rq
│   └── modality_coverage_stats.rq
│
└── 📁 assets/                         # 🖼️ Static images
    ├── logo.png
    └── tunnel_cross_section.png
```

---

## 🧭 Pages overview

| Icon | Page | What it shows |
|:----:|:-----|:--------------|
| 🏠 | **Overview** | Tunnel-level KPIs, section coverage, top priority defects |
| 📋 | **Defect Register** | All defects, filterable by type/priority/completeness, exportable |
| 🔬 | **Defect Detail** | One defect's full FMEA chain, modality evidence, intervention with standards refs |
| 💻 | **SPARQL Console** | Live query interface with pre-built example queries |
| 🔄 | **CV → COBie Bridge** | Demo of how CV pipeline output (masks, labels) becomes COBie rows |
| 🧠 | **Ontology Browser** | Class hierarchy, object/data properties, named individuals |

---

## 🎯 Key innovations demonstrated

### 1️⃣ Multi-level FMEA chain mapping

Each modality enters the FMEA reasoning chain at a *different* level:

| Modality | FMEA level | Answers |
|----------|------------|---------|
| 📷 **RGB** | Defect Condition | *What* is wrong? |
| 📐 **RGBD** | Measured Indicator | *How* severe? |
| 🌡️ **Thermal** | Potential Cause | *Why* is it happening? |
| 📡 **GPR** | Structure | *What's* inside? |

### 2️⃣ Diagnostic completeness scoring

For every defect, the system computes the fraction of FMEA chain levels with sensor evidence:

- 🟢 **4/4** → automated decision with full prescription
- 🟡 **3/4** → provisional decision with caveat
- 🟠 **2/4** → require additional survey before deciding
- 🔴 **1/4** → defect identified, full assessment deferred

### 3️⃣ Modality limitation awareness

The ontology explicitly encodes what each modality **cannot** detect (e.g. RGB cannot see subsurface delamination). When a missing chain level can only be filled by a modality that can't detect the relevant defect type, the system flags this rather than silently failing.

### 4️⃣ Australian regulatory grounding

Every prescribed intervention traces back to specific clauses in:

- 🇦🇺 **AS 5100** (Bridge design — Concrete)
- 🇦🇺 **AS 3600** (Concrete structures)
- 🇦🇺 **RMS Tunnel Inspection Manual**
- 🌍 **AASHTO Manual for Bridge Element Inspection** (Ch. 16 — tunnels)

---

## 🔌 Replacing the demo data with your own ontology

The repo ships with synthetic sample data so the app runs out of the box. To connect your real Protégé-authored ontology:

### Step 1 — Export from Protégé

1. Open your ontology in **Protégé 5.6+**
2. *File → Save As...*
3. Format: **Turtle**
4. Save as `ontology/tunnel_maintenance.ttl`

### Step 2 — Update namespace if needed

If your namespace differs from the default `http://tunnel-dt.transurban.com/ontology/v1.2#`:

📝 Edit `utils/ontology_loader.py`:

```python
TUN = Namespace("http://your-ontology-uri-here#")
```

### Step 3 — Reload

Click the **🔄 Reload ontology** button in the sidebar, or restart the app.

---

## ☁️ Deployment

### Streamlit Community Cloud (free)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. **New app** → connect your GitHub → select repo and branch (`main`)
4. **Main file path:** `app.py`
5. **Settings → Python version: 3.11** ⚠️ *Important — defaults to latest, which may break dependencies*
6. **Deploy**

> 🐛 **If you see "Error running app":** check the build log for clues. The most common issues are Python version mismatch (set to 3.11) and the first-run email prompt (handled by `[server] headless = true` in `.streamlit/config.toml`).

### Self-hosted

Any Linux server with Python 3.11:

```bash
git clone https://github.com/amandahuang-336/tunnel-dt2026.git
cd tunnel-dt2026
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Place behind nginx / Caddy for HTTPS.

---

## 🛠️ Tech stack

| Layer | Tool | Why |
|-------|------|-----|
| 🎨 **UI** | [Streamlit](https://streamlit.io/) | Rapid Python-native dashboards |
| 🧠 **Ontology** | [rdflib](https://rdflib.readthedocs.io/) | OWL/Turtle parsing + SPARQL |
| 📊 **Reasoning** | [owlrl](https://owl-rl.readthedocs.io/) | OWL 2 RL inference |
| 📈 **Charts** | [plotly](https://plotly.com/python/) | Interactive visualisations |
| 🐍 **Runtime** | Python 3.11 | Widest wheel support |

---

## 📖 Paper context

The framework operationalises a corrected understanding of multimodal tunnel inspection:

> *Each modality enters the FMEA reasoning chain at a different level, and the ontology maps these entry points explicitly, so that complementary evidence from different levels builds a complete diagnostic picture that no single modality could provide alone.*

This is **chain-level complementarity**, not same-level corroboration. It replaces the simpler (and physically inaccurate) framing that all modalities converge on a shared defect entity for Dempster-Shafer fusion.

---

## 📚 Citation

If this code or framework contributes to your research, please cite:

```bibtex
@article{huang2026serviceability,
  title   = {Serviceability-oriented Multimodal Data Integration
             for Tunnel Maintenance Digital Twins in the Australian
             Context},
  author  = {Huang, Mengqi and Rouhani, Matin and Zhu, Huamei and
             Li, Zhihang and Zhang, Qianbing},
  journal = {[Journal name]},
  year    = {2026}
}
```

---

## 🤝 Contributing

Contributions are warmly welcomed! Please:

1. 🍴 Fork the repo
2. 🌿 Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. ✏️ Commit your changes (`git commit -m 'Add amazing feature'`)
4. 📤 Push to the branch (`git push origin feature/AmazingFeature`)
5. 🔄 Open a Pull Request

Found a bug or have a feature request? [Open an issue](https://github.com/amandahuang-336/tunnel-dt2026/issues).

---

## 📝 License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for details.

---

## 🙏 Acknowledgements

- **Transurban** for operational context and inspection data discussions
- **Yu et al. (2021)** — *Tunnelling and Underground Space Technology* — for the COBie-to-OWL pattern this framework extends
- **Huang, Ninić, Zhang (2021)** — for the foundational CV-for-tunnel-defect work upstream of the CV→COBie bridge
- **Anthropic Claude** for development assistance through the build

---

<div align="center">

**Built with ☕ and ❤️ at Monash University**

If this helped your research, please ⭐ the repo!

[⬆ Back to top](#-tunnel-digital-twin--operator-dashboard)

</div>
