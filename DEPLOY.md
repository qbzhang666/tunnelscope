# Deploying the Tunnel-DT app (Docker)

A portable image that bundles the Streamlit app **and** TeX Live, so the
Step 8 PDF report and Beamer slide deck compile server-side. Runs on your
machine, a server, or any container host (Cloud Run, Azure Container Apps,
Render, Fly.io…).

## Quick start

```bash
docker compose up --build
# open http://localhost:8501
```

or with plain Docker:

```bash
docker build -t tunnel-dt:latest .
docker run --rm -p 8501:8501 tunnel-dt:latest
```

The build excludes the ~5 GB `2026 Ontology Paper` datasets (see
`.dockerignore`), so the context stays small. First build pulls TeX Live
(~1–1.5 GB installed); later builds are cached.

## What's in the image

- Python 3.13 + everything in `requirements.txt`.
- TeX Live (`texlive-latex-*`, fonts, pictures) for the report + Beamer deck.
- The app served **headless** on `0.0.0.0:8501` (overridden via env, so the
  committed `.streamlit/config.toml` still auto-opens a browser for local dev).

## Optional pieces

**Datasets (Standards Library + report References).** Optional — the app
degrades gracefully without them. To populate, mount the folder read-only
(uncomment in `docker-compose.yml`):

```yaml
- "/abs/path/to/2026 Ontology Paper:/app/2026 Ontology Paper:ro"
```

**Local VLM (Ollama).** The "AI auto-classify (local model)" / "Local LVM"
ingest routes need an Ollama endpoint. In a container `localhost` won't have
one, so either:

- use the **Cloud VLM** route or **manual entry** (no Ollama needed), or
- run the **Ollama sidecar**: uncomment the `ollama` service and
  `OLLAMA_ENDPOINT` in `docker-compose.yml`, then
  `docker compose exec ollama ollama pull qwen2.5vl:7b`.
  (The app reads `OLLAMA_ENDPOINT`; CPU by default, add an NVIDIA device
  reservation for GPU.)

**Persistence.** User-created tunnels are written to
`data/custom_tunnels.json` inside the container and reset on rebuild. To keep
them, bind-mount that one file (uncomment in compose). For true multi-user,
multi-tenant persistence use the FastAPI + database service in `backend/`.

## Slimming the image

If you don't need server-side PDFs, delete the TeX Live `RUN` block in the
`Dockerfile`. The app still works and offers the `.tex` / ZIP download so the
PDF can be compiled elsewhere — image drops to a few hundred MB.

## Auth (for "users access")

Streamlit has no built-in gate. Options:

- **Native OIDC** — `st.login()` is available on your `streamlit>=1.49`;
  configure an identity provider in `.streamlit/secrets.toml`.
- **Reverse proxy** — nginx basic-auth, oauth2-proxy, Cloudflare Access, or
  Tailscale in front of port 8501.
- **Platform auth** — if you push the image to Cloud Run (IAP) or Azure
  Container Apps (Easy Auth), let the platform handle it.

## Notes

- Health check uses Streamlit's `/_stcore/health` endpoint.
- LaTeX compiles run in a temp dir and stream back as bytes — no extra volume
  needed for report/deck output.
- The image is single-process; for many concurrent users put it behind a load
  balancer or scale horizontally (session state is per-connection).
