"""Security behaviour of the API foundation: headers, RBAC on audit, hash-chain integrity."""
from conftest import PASSWORD  # noqa: F401


def test_health_endpoint_reports_components(client):
    body = client.get("/health").json()
    assert body["status"] == "healthy"
    assert body["database"] == "ok" and body["storage"] == "ok" and body["api"] == "ok"
    assert body["ml"] == "not_configured"  # honest until Phase 5


def test_security_headers_present(client):
    api = client.get("/api/auth/me")
    assert api.headers["x-content-type-options"] == "nosniff"
    assert api.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in api.headers["content-security-policy"]
    assert api.headers["cache-control"] == "no-store"
    assert "x-request-id" in api.headers


def test_cors_only_allows_configured_origin(client):
    allowed = client.options("/api/auth/login", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    denied = client.options("/api/auth/login", headers={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in denied.headers


def test_unhandled_error_hides_stack_trace(client):
    from fastapi.testclient import TestClient

    from app.main import app

    def boom():
        raise RuntimeError("secret internal detail /etc/passwd")

    app.add_api_route("/__boom", boom, methods=["GET"])
    with TestClient(app, raise_server_exceptions=False) as quiet_client:
        response = quiet_client.get("/__boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "passwd" not in response.text and "Traceback" not in response.text


def test_audit_endpoints_are_rbac_protected(client, headers_for):
    assert client.get("/api/audit/logs").status_code == 401
    assert client.get("/api/audit/logs", headers=headers_for("ENGINEER")).status_code == 403
    assert client.get("/api/audit/logs", headers=headers_for("VIEWER")).status_code == 403
    assert client.get("/api/audit/logs", headers=headers_for("AUDITOR")).status_code == 200
    assert client.get("/api/audit/verify", headers=headers_for("ADMIN")).status_code == 200


def test_denied_access_is_audited(client, headers_for):
    client.get("/api/audit/logs", headers=headers_for("ENGINEER"))
    logs = client.get("/api/audit/logs", params={"action": "ACCESS_DENIED", "user": "t_engineer"},
                      headers=headers_for("AUDITOR")).json()
    assert logs["total"] >= 1 and logs["items"][0]["result"] == "FAILURE"


def test_rejected_token_is_audited(client, headers_for):
    client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    logs = client.get("/api/audit/logs", params={"action": "AUTH_TOKEN_REJECTED"},
                      headers=headers_for("AUDITOR")).json()
    assert logs["total"] >= 1


def test_audit_log_search_filters(client, headers_for):
    auditor = headers_for("AUDITOR")
    failures = client.get("/api/audit/logs", params={"result": "FAILURE"}, headers=auditor).json()
    assert failures["total"] >= 1 and all(i["result"] == "FAILURE" for i in failures["items"])
    assert client.get("/api/audit/logs", params={"result": "MAYBE"}, headers=auditor).status_code == 422
    assert client.get("/api/audit/logs", params={"limit": 100000}, headers=auditor).status_code == 422


def test_audit_details_never_contain_secrets(client, headers_for):
    client.post("/api/auth/login", json={"username": "nobody", "password": "SuperSecretPw123"})
    dump = client.get("/api/audit/logs", params={"limit": 500}, headers=headers_for("AUDITOR")).text
    assert "SuperSecretPw123" not in dump


def test_audit_chain_valid_then_detects_database_tampering(client, headers_for):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import AuditLog

    admin = headers_for("ADMIN")
    assert client.get("/api/audit/verify", headers=admin).json()["valid"] is True

    with SessionLocal() as db:
        row = db.execute(select(AuditLog).where(AuditLog.action == "LOGIN")
                         .order_by(AuditLog.id).limit(1)).scalar_one()
        row_id, original_user = row.id, row.user
        row.user = "attacker"  # simulate someone editing the database directly
        db.commit()
    try:
        verdict = client.get("/api/audit/verify", headers=admin).json()
        assert verdict["valid"] is False
        assert verdict["first_broken_id"] == row_id
    finally:
        with SessionLocal() as db:
            db.get(AuditLog, row_id).user = original_user
            db.commit()
    assert client.get("/api/audit/verify", headers=admin).json()["valid"] is True
