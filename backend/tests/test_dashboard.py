"""Dashboard summary and permission list returned to the frontend."""
from app.security.rbac import ROLE_PERMISSIONS

SUMMARY_KEYS = {"designs", "active_prints", "defects_detected", "incidents_open",
                "incidents_total", "parts", "supply_chain_events", "audit_events", "compliance"}


def test_summary_requires_authentication(client):
    assert client.get("/api/dashboard/summary").status_code == 401


def test_summary_returns_live_counts_for_every_role(client, headers_for):
    for role in ROLE_PERMISSIONS:
        response = client.get("/api/dashboard/summary", headers=headers_for(role))
        assert response.status_code == 200, role
        body = response.json()
        assert SUMMARY_KEYS <= set(body)
        assert all(isinstance(body[k], int) and body[k] >= 0 for k in SUMMARY_KEYS - {"compliance"})
        assert set(body["compliance"]) == {"pass_count", "fail_count", "unknown_count", "total"}


def test_summary_audit_count_reflects_database(client, headers_for):
    before = client.get("/api/dashboard/summary", headers=headers_for("VIEWER")).json()
    client.post("/api/auth/login", json={"username": "nobody", "password": "wrong-password"})
    after = client.get("/api/dashboard/summary", headers=headers_for("VIEWER")).json()
    assert after["audit_events"] > before["audit_events"]


def test_me_includes_permissions_matching_rbac_table(client, headers_for):
    for role, expected in ROLE_PERMISSIONS.items():
        body = client.get("/api/auth/me", headers=headers_for(role)).json()
        assert set(body["permissions"]) == {p.value for p in expected}, role
