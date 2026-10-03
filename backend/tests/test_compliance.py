"""Compliance checks inspect the live system; they must never report a fake PASS."""
from app.services import compliance as svc


def test_requires_authentication(client):
    assert client.get("/api/compliance/controls").status_code == 401
    assert client.post("/api/compliance/run").status_code == 401


def test_only_roles_with_compliance_view_may_use_it(client, headers_for):
    for role in ("VIEWER", "ENGINEER", "QUALITY_INSPECTOR", "SUPPLY_CHAIN"):
        assert client.post("/api/compliance/run", headers=headers_for(role)).status_code == 403, role
    for role in ("ADMIN", "AUDITOR"):
        assert client.post("/api/compliance/run", headers=headers_for(role)).status_code == 200, role


def test_run_returns_every_control_with_evidence(client, headers_for):
    body = client.post("/api/compliance/run", headers=headers_for("AUDITOR")).json()
    assert body["total"] == len(svc.CONTROLS)
    assert body["pass_count"] + body["fail_count"] + body["unknown_count"] == body["total"]
    assert "not a certification" in body["disclaimer"]
    for control in body["controls"]:
        assert control["status"] in {"PASS", "FAIL", "UNKNOWN"}
        assert control["evidence"] and control["last_checked"]


def test_controls_are_persisted_and_feed_the_dashboard(client, headers_for):
    run = client.post("/api/compliance/run", headers=headers_for("ADMIN")).json()
    stored = client.get("/api/compliance/controls", headers=headers_for("AUDITOR")).json()
    assert stored["total"] == run["total"]
    summary = client.get("/api/dashboard/summary", headers=headers_for("VIEWER")).json()
    assert summary["compliance"]["total"] == run["total"]
    assert summary["compliance"]["pass_count"] == run["pass_count"]


def test_core_security_controls_pass_on_a_healthy_system(client, headers_for):
    body = client.post("/api/compliance/run", headers=headers_for("ADMIN")).json()
    by_ref = {c["control_ref"]: c["status"] for c in body["controls"] if c["framework"] == "NIST"}
    for ref in ("PR.AC-1", "PR.AC-4", "PR.AC-7", "PR.DS-1", "PR.PT-1"):
        assert by_ref[ref] == "PASS", ref


def test_tampered_audit_log_turns_the_integrity_control_into_fail(client, headers_for):
    from sqlalchemy import update

    from app.database import SessionLocal
    from app.models import AuditLog

    with SessionLocal() as db:
        first = db.query(AuditLog).order_by(AuditLog.id).first()
        original = first.user
        db.execute(update(AuditLog).where(AuditLog.id == first.id).values(user="attacker"))
        db.commit()
    try:
        body = client.post("/api/compliance/run", headers=headers_for("ADMIN")).json()
        status = {c["control_ref"]: c["status"] for c in body["controls"]}
        assert status["PR.PT-1"] == "FAIL"
        assert status["7.5.3"] == "FAIL"
    finally:
        with SessionLocal() as db:
            db.execute(update(AuditLog).where(AuditLog.id == first.id).values(user=original))
            db.commit()
    again = client.post("/api/compliance/run", headers=headers_for("ADMIN")).json()
    assert {c["control_ref"]: c["status"] for c in again["controls"]}["PR.PT-1"] == "PASS"
