"""Runtime settings (12-factor) — read from env / .env, with dev defaults."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite for zero-setup dev; swap to postgresql+psycopg://… in production.
    database_url: str = "sqlite:///./tunnel_dt.db"

    # Auth. Dev mode mints/verifies HS256 tokens locally so the API is
    # runnable without an IdP. In production set auth_dev_mode=false and
    # configure the OIDC issuer/audience (RS256 verified via JWKS).
    auth_dev_mode: bool = True
    jwt_secret: str = "dev-only-change-me-to-a-real-32byte+-secret"
    jwt_alg: str = "HS256"
    jwt_ttl_minutes: int = 720
    oidc_issuer: Optional[str] = None
    oidc_audience: Optional[str] = None

    # Where the Streamlit repo (with utils/) lives, if not the parent dir.
    repo_root: Optional[str] = None

    cors_origins: str = "http://localhost:8501"


settings = Settings()
