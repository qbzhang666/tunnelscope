# syntax=docker/dockerfile:1
#
# Tunnel-DT — Streamlit app, portable image.
#
# Bundles TeX Live so the Step 8 PDF report and Beamer slide deck compile
# server-side. The ~5 GB "2026 Ontology Paper" datasets are excluded from the
# build context (.dockerignore) and optional at runtime — mount them
# read-only if you want the Standards Library / report References populated.

FROM python:3.13-slim

# --- TeX Live for the LaTeX report + Beamer deck -----------------------------
# The app runs without this (it offers a .tex / ZIP fallback), so you can
# delete this block for a much smaller image if server-side PDFs aren't needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
        texlive-latex-base \
        texlive-latex-recommended \
        texlive-latex-extra \
        texlive-fonts-recommended \
        texlive-pictures \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python dependencies (own layer for build caching) -----------------------
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# --- Application code ---------------------------------------------------------
COPY . .

# Streamlit served headless on all interfaces. The committed
# .streamlit/config.toml is left untouched (local dev still auto-opens a
# browser); these env vars override only inside the container.
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_RUNONSAVE=false \
    STREAMLIT_BROWSER_GATHERUSAGESTATS=false

EXPOSE 8501

# Streamlit's own health endpoint returns "ok" when the server is ready.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health').read().strip()==b'ok' else 1)"

CMD ["streamlit", "run", "app.py"]
