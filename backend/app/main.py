"""FastAPI app entrypoint.

    uvicorn app.main:app --reload     # from the backend/ directory
    open http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (register tables on the metadata)
from .config import settings
from .db import Base, engine
from .routers import auth, defects, health, tunnels

app = FastAPI(
    title="Tunnel DT API",
    version="0.1.0",
    summary="Production skeleton — reuses the Streamlit app's utils/ domain code.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dev convenience: auto-create tables. Production uses Alembic migrations.
Base.metadata.create_all(bind=engine)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(tunnels.router)
app.include_router(defects.router)
