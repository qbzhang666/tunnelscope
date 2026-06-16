# Tunnel Digital Twin — Operator Dashboard

A serviceability-oriented **multimodal tunnel-maintenance digital twin**. It
turns inspection findings into a costed, standards-backed maintenance plan:
defects are placed on a 3-D segmental-lining model, diagnosed through a
7-level FMEA chain in an OWL ontology, costed with a transparent unit-rate
model, and rolled up into a board-ready **PDF report and slide deck**.

> **Try it online (nothing to install):**
> https://amandahuang-336-tunnel-dt2026-app-zmguxo.streamlit.app/

---

## What you get

- Register tunnels and view a parametric **segmental-lining 3-D BIM** (lining
  thickness, segments per ring, keystone) with every defect at its surveyed
  position. Upload your own **scan-to-BIM** mesh or point cloud, and export
  the model to **IFC**.
- Log inspection findings by hand, or with **AI defect recognition** from a
  photo or written report — a local model (Ollama) or a cloud vision model.
- Diagnose each defect through a **7-level FMEA chain**
  (component → mechanism → defect → indicator → cause → threshold →
  intervention) reasoned over an OWL ontology, with a **priority** and a
  transparent **cost** build-up.
- Trace every prescription to the **standard** behind it (AASHTO / Austroads /
  fib), export **COBie** rows, query the knowledge base with **SPARQL**, and
  generate a **PDF report + Beamer presentation**.

---

## Download

Clone the repository:

```bash
git clone https://github.com/Amandahuang-336/Tunnel-DT2026.git
cd Tunnel-DT2026
```

…or on GitHub click **Code → Download ZIP** and unzip it.

> The ~5 GB `2026 Ontology Paper` datasets folder is **not** in the repo (it is
> git-ignored). The app runs fine without it; the Standards Library and the
> report's References section simply show less. See
> [Standards Library data](#standards-library-data) to add it.

---

## Install & run

Pick whichever fits you. All three serve the app at <http://localhost:8501>.

### Option A — Docker (any OS, recommended)

Self-contained: bundles Python, all dependencies, **and** TeX Live so the PDF
report and slide deck compile in the container.

**Requires:** [Docker Desktop](https://www.docker.com/products/docker-desktop/)
(or Docker Engine + Compose).

```bash
docker compose up --build
# then open http://localhost:8501
```

Full deployment details — datasets mount, an Ollama sidecar, persistence,
auth, slimming the image — are in **[DEPLOY.md](DEPLOY.md)**.

### Option B — Windows, one click

**Requires:** Python 3.11+ on `PATH` (3.13 recommended) — from
<https://www.python.org/> or the Microsoft Store.

Double-click **`run_local.cmd`**. The first run builds an isolated environment
(1–3 minutes); afterwards it starts in seconds and opens your browser
automatically. Details and options (custom port, rebuild) are in
**[RUN_LOCAL.md](RUN_LOCAL.md)**.

### Option C — Manual (any OS)

**Requires:** Python 3.11+ (3.13 recommended).

```bash
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

For the PDF report and slide deck, also install a TeX distribution —
[MiKTeX](https://miktex.org/) (Windows) or
[TeX Live](https://tug.org/texlive/) (macOS/Linux). This is **optional**: without
it the app still runs and lets you download the `.tex` source to compile
elsewhere.

---

## How to use it

The sidebar is a numbered workflow — work top to bottom. A typical session:

| Step | Page | What you do |
|---|---|---|
| 1 | **Overview** | Orientation: the workflow diagram and what the app does. |
| 2 | **Tunnel Setup** | Pick a sample tunnel or register your own (length, diameter, ring size). |
| 3 | **3D Tunnel (BIM)** | See the segmental-lining model + a true-scale ring cross-section; tune the geometry; **upload a scan-to-BIM mesh/point cloud**; export **IFC**. |
| 4 | **Ingest a finding** | Log a defect — manually, or let **AI** recognise it from a photo or report (see below). |
| 5 | **Defect Register** | Every defect for the tunnel, on a map and in a table. |
| 6 | **Defect Detail** | One defect's FMEA chain, cause, prescribed intervention and cost build-up; **export COBie rows**; raise a work order. |
| 7 | **Standards Library** | The standards each prescription cites (needs the datasets folder). |
| 8 | **Report & presentation** | Generate the **PDF report** and the **Beamer slide deck** for the whole session. |

**Expert tools** (optional, off the main path): a **SPARQL console** to query
the knowledge base, the **CV → COBie bridge**, and an **ontology browser**.
Their outputs can also be folded into the Step 8 report.

---

## Optional features

### AI defect recognition (Step 4)

On the Ingest page, "Extraction method" offers:

- **AI auto-classify (local model)** and **Local LVM** — run a vision model on
  your own machine via [Ollama](https://ollama.com/). Install Ollama, then
  pull a vision model once:
  ```bash
  ollama pull qwen2.5vl:7b
  ```
  The first classification loads the model into memory and is slow; later ones
  are fast. (In Docker, run an Ollama sidecar and set `OLLAMA_ENDPOINT` — see
  [DEPLOY.md](DEPLOY.md).)
- **Cloud VLM (Claude / OpenAI / Gemini)** — no local model; paste your own API
  key into the panel. Use this if you don't have Ollama.
- **Manual / Heuristic** — no model needed at all.

### PDF report & slide deck (Step 8)

Needs a TeX engine (bundled in the Docker image; install MiKTeX / TeX Live for
the local options). Without one, the app still produces the `.tex` source and a
ZIP so you can compile the PDF elsewhere.

### Standards Library data

To populate the Standards Library and the report's References, place the
`2026 Ontology Paper` folder (standards PDFs + datasets) at the repository
root. The app detects it automatically and degrades gracefully when it is
absent.

---

## Project layout

```
app.py                 Streamlit entry point + sidebar/workflow router
pages/                 The numbered workflow pages (0_Ingest … 8_Report)
utils/                 Domain logic: ontology, FMEA, cost model, BIM 3-D,
                       IFC + scan import, COBie, report/presentation, VLM
ontology/              The OWL/Turtle maintenance ontology
data/                  Seed tunnel geometry + BIM as-built records
backend/               Optional FastAPI + SQLAlchemy service (multi-user path)
Dockerfile,            Containerised deployment (see DEPLOY.md)
docker-compose.yml
run_local.cmd          Windows one-click launcher (see RUN_LOCAL.md)
requirements.txt       Python dependencies
```

---

## Troubleshooting

- **Port 8501 already in use** — run on another port: `streamlit run app.py
  --server.port 8600`, `run_local.cmd 8600`, or change the published port in
  `docker-compose.yml`.
- **PDF won't compile** — no TeX engine found. Install MiKTeX / TeX Live, or use
  the Docker image, or download the offered `.tex` / ZIP and compile elsewhere.
- **AI classification times out** — a local model's first run is a cold start;
  click again (it's warm now) or raise the timeout in the Ingest config panel.
  No Ollama? Use the Cloud VLM route or manual entry.
- **Maps are blank** — the defect maps use OpenStreetMap tiles, which need
  internet. The rest of the app (ontology, SPARQL, COBie, reports) works offline.
- **Standards Library is empty** — add the `2026 Ontology Paper` folder (see
  above); it's optional.

---

## Deployment

For a shared/hosted instance — container hosts, the optional Ollama sidecar,
persistence, and authentication options — see **[DEPLOY.md](DEPLOY.md)**. For a
true multi-user, database-backed service, see the FastAPI skeleton in
**[backend/](backend/README.md)**.

---

## Data & license

The bundled tunnels, BIM records and geological context are **synthetic
demonstration data** — anonymised and standards-consistent, not real operator
records. This is the companion app to the research paper *Serviceability-oriented
Multimodal Data Integration for Tunnel Maintenance Digital Twins in the
Australian Context*; please cite it if you build on this work.
