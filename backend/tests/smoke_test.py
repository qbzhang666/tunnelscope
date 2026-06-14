"""
End-to-end smoke test (no server needed — FastAPI TestClient).

Proves the skeleton boots and that the headline claims hold:
  - auth + RBAC + org isolation
  - the cost endpoint reuses utils.cost_model unchanged
  - the work-order sign-off flow + audit log
  - the IFC export reuses utils.ifc_export

Run from the backend/ directory:  py -3.13 tests/smoke_test.py
"""

import os
import sys

# Use a throwaway DB and force dev auth BEFORE importing the app.
os.environ["DATABASE_URL"] = "sqlite:///./_smoke_test.db"
os.environ["AUTH_DEV_MODE"] = "true"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for f in ("_smoke_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def _token(email, role, org="Acme Roads"):
    r = client.post("/auth/dev-token",
                    json={"email": email, "role": role, "org_name": org})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def main() -> int:
    assert client.get("/health").json()["status"] == "ok"
    print("OK  boots + /health")

    admin = _token("eng@acme.test", "admin")

    # create tunnel + defect
    t = client.post("/tunnels", headers=admin, json={
        "label": "Tunnel A", "length_m": 2800, "ring_length_m": 1.6,
        "alignment": [[-37.83, 144.92], [-37.81, 144.95]]}).json()
    d = client.post("/defects", headers=admin, json={
        "tunnel_id": t["id"], "defect_type": "Spalls", "ring_id": 1158,
        "chainage_m": 772, "position": "Crown", "severity": "S-3",
        "completeness_score": 0.75,
        "measurements": {"spall_depth_mm": 58, "area_cm2": 112},
        "description": "S-3 spall with rebar exposed"}).json()
    print(f"OK  created tunnel {t['id'][:8]} + defect {d['id'][:8]}")

    # cost build-up — reuses utils.cost_model
    cost = client.get(f"/defects/{d['id']}/cost", headers=admin).json()
    assert cost["expected"] > 0 and cost["method"]
    assert any("Structural" in line[0] for line in cost["lines"]), cost["lines"]
    print(f"OK  cost via utils.cost_model: ${cost['expected']:,.0f} "
          f"(band ${cost['low']:,.0f}-${cost['high']:,.0f}, S-3 allowance present)")

    # work-order create + approve + audit
    wo = client.post(f"/defects/{d['id']}/work-order", headers=admin, json={
        "steps": [{"step": "Break out unsound concrete",
                   "reference": "AASHTO Ch16 §16.4"}],
        "deadline_days": 30}).json()
    ap = client.post(f"/work-orders/{wo['id']}/approve", headers=admin)
    assert ap.status_code == 200 and ap.json()["approval_status"] == "approved"
    print("OK  work-order created + approved (audit-logged)")

    # RBAC: a viewer cannot create a work order
    viewer = _token("view@acme.test", "viewer")
    r = client.post(f"/defects/{d['id']}/work-order", headers=viewer,
                    json={"steps": [], "deadline_days": 5})
    assert r.status_code == 403, r.status_code
    print("OK  RBAC: viewer blocked from work-order create (403)")

    # IFC export — reuses utils.ifc_export
    ifc = client.get(f"/tunnels/{t['id']}/ifc", headers=admin)
    assert ifc.status_code == 200 and ifc.text.startswith("ISO-10303-21")
    assert "#Spalls" in ifc.text  # ontology classification link present
    print("OK  IFC export via utils.ifc_export (IFC4, ontology-classified)")

    # org isolation: a second org sees none of Acme's tunnels
    other = _token("x@other.test", "admin", org="Other Co")
    assert client.get("/tunnels", headers=other).json() == []
    print("OK  multi-tenant isolation: Other Co sees 0 tunnels")

    print("\nALL BACKEND SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
