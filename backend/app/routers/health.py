from fastapi import APIRouter

from ..config import settings

router = APIRouter(tags=["meta"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/")
def root():
    return {
        "name": "Tunnel DT API",
        "version": "0.1.0",
        "docs": "/docs",
        "auth_dev_mode": settings.auth_dev_mode,
    }
