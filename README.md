# Tunnel Digital Twin — Operator Dashboard

Streamlit web application accompanying the paper:

> **Serviceability-oriented Multimodal Data Integration for Tunnel
> Maintenance Digital Twins in the Australian Context.**

This dashboard is the human-facing interface to a populated ontology of
road tunnel defects, FMEA chains, and prescribed interventions. It
queries the ontology through `rdflib` (a Python alternative to Apache
Jena Fuseki) and presents the results in an operator-friendly UI.

## Architecture

```
Protégé (authoring)
    │
    ▼  OWL / Turtle file
tunnel_maintenance.ttl
    │
    ▼  rdflib loads into memory
Streamlit app
    │
    ├─ SPARQL queries on page load
    └─ User sees defects, FMEA chains, interventions
```

## Quickstart

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd tunnel_dt_streamlit

# 2. Install dependencies (Python 3.9+)
pip install -r requirements.txt

# 3. Run the app
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## File structure

```
tunnel_dt_streamlit/
├── app.py                          # Main entry — overview page
├── requirements.txt                # Python dependencies
├── README.md                       # This file
│
├── .streamlit/
│   └── config.toml                 # Streamlit theme and server config
│
├── pages/                          # Multipage Streamlit pages
│   ├── 1_Defect_Register.py        # Ranked list of all defects
│   ├── 2_Defect_Detail.py          # Full FMEA chain for one defect
│   ├── 3_SPARQL_Console.py         # Interactive query interface
│   ├── 4_CV_to_COBie_Bridge.py     # Defect semantic extraction demo
│   └── 5_Ontology_Browser.py       # Class hierarchy and relations
│
├── utils/                          # Reusable backend modules
│   ├── __init__.py
│   ├── ontology_loader.py          # Load and cache the ontology
│   ├── sparql_queries.py           # Pre-built SPARQL query strings
│   ├── fmea_chain.py               # Chain traversal and completeness
│   ├── cv_to_cobie.py              # CV output → COBie row conversion
│   └── styling.py                  # Custom CSS
│
├── ontology/                       # TBox (schema) files
│   ├── tunnel_maintenance.ttl      # Your Protégé export
│   ├── cobie_ontology.ttl          # COBie ontology layer
│   └── austroads_rads.ttl          # Austroads RADS ontology layer
│
├── data/                           # ABox (instance) files
│   ├── defects_tunnel_a.json       # Defect instances for demo
│   ├── cv_detections_sample.json   # Example CV pipeline output
│   └── cobie_rows_sample.csv       # Example COBie spreadsheet rows
│
├── queries/                        # Saved SPARQL queries
│   ├── all_defects_by_ring.rq
│   ├── completeness_score.rq
│   ├── high_priority_defects.rq
│   ├── fmea_chain_for_defect.rq
│   └── modality_coverage_stats.rq
│
└── assets/                         # Static images
    ├── logo.png
    └── tunnel_cross_section.png
```

## Replacing the sample data

The repo ships with synthetic sample data so the app runs out of the
box. To connect your real ontology:

1. **Export from Protégé** → *Save As* → Turtle (`.ttl`).
2. Place the file at `ontology/tunnel_maintenance.ttl`.
3. If your namespace is not `http://tunnel-dt.transurban.com/ontology/v1.2#`,
   edit `utils/ontology_loader.py` and update the `TUN` prefix.
4. Restart the Streamlit app.

## Deployment

- **Streamlit Community Cloud (free):** push to GitHub, connect repo
  at share.streamlit.io. Public URL in minutes.
- **Self-hosted:** any server with Python 3.9+. Streamlit works behind
  nginx; bind `streamlit run app.py --server.port 8501 --server.address 0.0.0.0`.

## Citation

If this code contributes to your work, please cite:

```bibtex
@article{huang2026serviceability,
  title   = {Serviceability-oriented Multimodal Data Integration
             for Tunnel Maintenance Digital Twins in the Australian
             Context},
  author  = {Huang, Mengqi and Rouhani, Matin and Zhu, Huamei and
             Li, Zhihang and Zhang, Qianbing},
  journal = {...},
  year    = {2026}
}
```

## License

MIT. See `LICENSE`.
