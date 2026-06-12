# Running the Tunnel Digital Twin locally

This dashboard is deployed on Streamlit Community Cloud, but it also runs
entirely on your own machine — no cloud account, no internet required for the
app itself (only map tiles fetch from the web; see Notes).

## Quick start (Windows)

**Double-click `run_local.cmd`.**

That's it. The first run sets things up (1–3 minutes); after that it starts in
a few seconds. A browser tab opens automatically at <http://localhost:8501>.

To stop the app, close the console window or press `Ctrl+C` in it.

### From a terminal

```bat
run_local.cmd            :: set up if needed, then launch on port 8501
run_local.cmd 8600       :: launch on a different port
run_local.cmd clean      :: delete the environment and rebuild from scratch
```

## What `run_local.cmd` does

1. Finds a Python interpreter (`py -3` or `python`).
2. Creates an **isolated virtual environment** at
   `%USERPROFILE%\.tunnel-dt2026-venv` (i.e. `C:\Users\<you>\.tunnel-dt2026-venv`).
   It is deliberately kept **outside** this project folder because:
   - the project lives on a **Google Shared Drive**, and a venv inside it
     would be re-synced constantly (thousands of files) — slow and fragile; and
   - it is kept **out of `AppData`** so the Microsoft Store build of Python
     (which redirects venvs created under `AppData` into its sandbox) puts the
     environment where we expect.
3. Installs the dependencies from `requirements.txt` on the first run. It only
   reinstalls when `requirements.txt` changes (it stores a hash), so normal
   launches are fast.
4. Starts Streamlit (`streamlit run app.py`) and opens your browser.

The file watcher is disabled by default so Google Drive sync activity can't
trigger reloads that drop your in-session data. Pass a port number to change
the port; pass `clean` to rebuild the environment.

> Override the environment location with the `TUNNEL_DT_VENV` environment
> variable if you want it somewhere else.

## Prerequisites

- **Python 3.11 or newer** on `PATH` (3.13 is what this machine uses and is
  fully supported). Get it from <https://www.python.org/> or the Microsoft
  Store. The Microsoft Store build works fine with this launcher.

That is the only requirement. Everything else is installed into the isolated
environment.

## Notes

- **Why a `.cmd` and not a `.ps1`?** Google Drive stamps synced files with a
  "Mark of the Web", and on a managed/Enterprise machine that blocks unsigned
  PowerShell scripts even with `-ExecutionPolicy Bypass`. A batch file is not
  subject to that, so it just runs.
- **Maps need internet.** The defect maps use folium/OpenStreetMap tiles, which
  load from the web. The rest of the app (ontology, SPARQL, COBie bridge) is
  fully offline.
- **Local LVM mode actually works here.** The Ingest page's
  *Local LVM (Ollama / Qwen)* option talks to a model server on your machine.
  Ollama is installed on this workstation — start it (`ollama serve`) and pull a
  vision model (e.g. `ollama pull qwen2.5vl:7b`) to use it. This mode does not
  work on the cloud deployment.
- **`verify_owlrl.py`.** This optional script checks the OWL 2 RL reasoner. Its
  strict subclass-materialisation check is tuned for the cloud's older `rdflib`
  (6.x on Python 3.11); on a current local stack (`rdflib` 7.x, Python 3.13) the
  reasoner runs but does not make `rdfs:subClassOf` reflexive, so that check
  reports FAIL. **The dashboard itself is unaffected** — defect queries use a
  property-path fallback by design, and the app shows the correct defect set.

## Manual alternative (any OS)

If you prefer to manage your own environment (or are on macOS/Linux):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On macOS/Linux there is no Google Drive Mark-of-the-Web issue, so a venv inside
the project is fine (it is already covered by `.gitignore`).
