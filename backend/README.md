# Tunnel DT — production API skeleton

A lean **FastAPI + SQLAlchemy** backend that turns the Streamlit demo into
something multi-user and database-backed — **without rewriting the domain
logic**. The cost model, IFC export, FMEA, and report code in the parent
`utils/` are imported and reused unchanged (see `app/domain.py`).

It runs out of the box on **SQLite** with **dev-mode auth** (no IdP needed),
and is written to switch to **PostgreSQL + PostGIS** and **OIDC/SSO** by
changing config only.

## Quick start

```bash
cd backend
py -3.13 -m pip install -r requirements.txt
py -3.13 -m uvicorn app.main:app --reload
# open http://localhost:8000/docs
```

Get a dev token (Swagger UI → `POST /auth/dev-token`, or curl):

```bash
curl -X POST localhost:8000/auth/dev-token \
  -H "content-type: application/json" \
  -d '{"email":"eng@acme.test","role":"engineer","org_name":"Acme Roads"}'
```

Use the returned `access_token` as `Authorization: Bearer <token>` on the
other endpoints. Run the end-to-end check:

```bash
py -3.13 tests/smoke_test.py
```

## What's here

| Area | File | Notes |
|---|---|---|
| **Data model** | `app/models.py` | Org, User, Tunnel(+segment/geology), Inspection, Defect, ModalityObservation, Intervention, CostEstimate, Artifact, AuditLog |
| **Auth / RBAC** | `app/auth.py` | dev HS256 now, OIDC RS256 (JWKS) seam for production; `require_role()`; org scoping |
| **Reuse bridge** | `app/domain.py` | ORM row → plain dict → existing `utils/` functions |
| **API** | `app/routers/` | tunnels (+IFC export), defects (+cost, work-order sign-off), auth, health |
| **Audit** | `app/audit.py` | every create/approve/export recorded |

## Endpoints (implemented)

- `POST /auth/dev-token` — local token (dev mode only)
- `GET/POST /tunnels`, `GET /tunnels/{id}`, `GET /tunnels/{id}/ifc`
- `GET/POST /defects`, `GET /defects/{id}`
- `GET /defects/{id}/cost` — **reuses `utils.cost_model`**
- `POST /defects/{id}/work-order` (engineer), `POST /work-orders/{id}/approve` (approver)

Other tables in the model (segments, geology, inspections, artifacts) follow
the same router pattern — add them as the pilot needs.

## Production switches (config only)

- **Postgres + PostGIS:** set `DATABASE_URL=postgresql+psycopg://…`; change
  `Tunnel.alignment` to `geometry(LineString,4326)` via GeoAlchemy2; add
  Postgres Row-Level Security on `org_id`. Replace `create_all` with Alembic.
- **OIDC/SSO:** set `AUTH_DEV_MODE=false` + `OIDC_ISSUER`/`OIDC_AUDIENCE`;
  `auth._decode` already verifies RS256 against the issuer's JWKS.
- **Object storage:** the `Artifact` table holds storage keys; wire S3/Blob
  in an `app/storage.py` and stream uploads/downloads there.
- **Async workers:** move VLM classify, LaTeX/PDF, OWL reasoning, and IFC
  export onto a Redis queue (RQ/Celery); the domain functions are already
  pure and queue-friendly.

## Known coupling to clean up

`utils.ifc_export` transitively imports plotly/folium (via `bim3d`/`gis`)
because the Streamlit app shares helpers there. Lift the pure functions
(`PRIORITY_COLOURS`, `position_to_angle_deg`) into a UI-free module so the
backend doesn't drag UI libraries. Until then, run the backend in the same
environment as the Streamlit app.
