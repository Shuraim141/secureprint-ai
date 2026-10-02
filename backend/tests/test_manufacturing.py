"""Manufacturing security API: printer simulator, anomaly detection, G-code analysis,
automated incident response (Modules F/G/H/I/K)."""
import time

from sqlalchemy import select

from app.database import SessionLocal
from app.models import SecurityEvent

GCODE_DIR = __import__("pathlib").Path(__file__).resolve().parents[2] / "manufacturing" / "gcode"


def gcode_file(name: str) -> bytes:
    return (GCODE_DIR / f"{name}.gcode").read_bytes()


def get_printer_id(client, headers) -> int:
    printers = client.get("/api/manufacturing/printers", headers=headers).json()
    assert printers, "expected at least one seeded printer"
    return printers[0]["id"]


def wait_until(predicate, timeout_s: float = 8.0, interval_s: float = 0.2):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(interval_s)
    raise AssertionError(f"condition not met within {timeout_s}s")


def stop_all(client, headers):
    for printer in client.get("/api/manufacturing/printers", headers=headers).json():
        client.post(f"/api/manufacturing/printers/{printer['id']}/stop", headers=headers)


# ---------------- access control ----------------
def test_manufacturing_endpoints_require_permission(client, headers_for, trained_models):
    printer_id = get_printer_id(client, headers_for("ADMIN"))
    for role in ("VIEWER", "AUDITOR", "SUPPLY_CHAIN"):  # none of these have printer:control
        assert client.post(f"/api/manufacturing/printers/{printer_id}/start",
                           headers=headers_for(role), json={"scenario": "NORMAL"}).status_code == 403
    assert client.get("/api/manufacturing/printers", headers=headers_for("VIEWER")).status_code == 200
    # incident:view: ENGINEER, QUALITY_INSPECTOR, AUDITOR and VIEWER all have it by design
    # (see rbac.py); SUPPLY_CHAIN is the one role that does not.
    assert client.get("/api/manufacturing/incidents", headers=headers_for("VIEWER")).status_code == 200
    assert client.get("/api/manufacturing/incidents", headers=headers_for("AUDITOR")).status_code == 200
    assert client.get("/api/manufacturing/incidents",
                      headers=headers_for("SUPPLY_CHAIN")).status_code == 403


# ---------------- printer simulator lifecycle ----------------
def test_start_normal_print_runs_to_completion_with_no_incident(client, headers_for, trained_models):
    engineer = headers_for("ENGINEER")
    printer_id = get_printer_id(client, engineer)
    stop_all(client, engineer)

    started = client.post(f"/api/manufacturing/printers/{printer_id}/start", headers=engineer,
                          json={"scenario": "NORMAL", "seed": 123})
    assert started.status_code == 201, started.text
    assert started.json()["simulator_state"] == "RUNNING"

    telemetry = client.get(f"/api/manufacturing/printers/{printer_id}/telemetry",
                           headers=engineer).json()
    assert telemetry["printer_id"] == printer_id

    def completed():
        body = client.get(f"/api/manufacturing/printers/{printer_id}/telemetry",
                          headers=engineer).json()
        return body if body["simulator_state"] in {"COMPLETED", "IDLE"} else None

    # 15 ticks x 0.5s (the "high" profile tick rate conftest.py selects for tests) = 7.5s
    # minimum; 20s leaves comfortable margin for test overhead.
    final = wait_until(completed, timeout_s=20.0)
    assert not any(s["anomaly"] for s in final["samples"])
    stop_all(client, engineer)


def test_duplicate_start_is_rejected(client, headers_for, trained_models):
    engineer = headers_for("ENGINEER")
    printer_id = get_printer_id(client, engineer)
    stop_all(client, engineer)
    first = client.post(f"/api/manufacturing/printers/{printer_id}/start", headers=engineer,
                        json={"scenario": "NORMAL", "seed": 1})
    assert first.status_code == 201
    again = client.post(f"/api/manufacturing/printers/{printer_id}/start", headers=engineer,
                       json={"scenario": "NORMAL", "seed": 1})
    assert again.status_code == 409
    stop_all(client, engineer)


def test_unknown_scenario_is_rejected_by_validation(client, headers_for, trained_models):
    engineer = headers_for("ENGINEER")
    printer_id = get_printer_id(client, engineer)
    response = client.post(f"/api/manufacturing/printers/{printer_id}/start", headers=engineer,
                           json={"scenario": "MELTDOWN"})
    assert response.status_code == 422


def test_start_stop_unknown_printer_404(client, headers_for, trained_models):
    engineer = headers_for("ENGINEER")
    assert client.post("/api/manufacturing/printers/999999/start", headers=engineer,
                       json={"scenario": "NORMAL"}).status_code == 404
    assert client.get("/api/manufacturing/printers/999999/telemetry",
                      headers=engineer).status_code == 404


# ---------------- automated incident response (Demo 6 / Demo 3) ----------------
def test_overheat_triggers_full_incident_response_chain(client, headers_for, trained_models):
    """Telemetry -> detection -> security event -> incident -> simulated pause -> audit log,
    end to end through the real HTTP API and the real background asyncio task."""
    engineer = headers_for("ENGINEER")
    printer_id = get_printer_id(client, engineer)
    stop_all(client, engineer)

    before_incidents = client.get("/api/manufacturing/incidents", headers=headers_for("AUDITOR")
                                  ).json()["total"]
    client.post(f"/api/manufacturing/printers/{printer_id}/start", headers=engineer,
               json={"scenario": "OVERHEAT", "seed": 42})

    def paused():
        body = client.get(f"/api/manufacturing/printers/{printer_id}/telemetry",
                          headers=engineer).json()
        return body if body["simulator_state"] == "PAUSED" else None

    telemetry = wait_until(paused, timeout_s=15.0)
    assert any(s["anomaly"] for s in telemetry["samples"])

    incidents = client.get("/api/manufacturing/incidents", headers=headers_for("AUDITOR")).json()
    assert incidents["total"] == before_incidents + 1
    incident = incidents["items"][0]
    assert incident["action_taken"] == "PRINT_PAUSED" and incident["status"] == "OPEN"
    assert incident["printer_id"] == printer_id

    with SessionLocal() as db:
        events = db.execute(select(SecurityEvent).where(
            SecurityEvent.incident_id == incident["id"])).scalars().all()
    assert events and events[0].severity == "HIGH"

    logs = client.get("/api/audit/logs", params={"action": "PRINTER_START"},
                      headers=headers_for("AUDITOR")).json()
    assert logs["total"] >= 1
    stop_all(client, engineer)


# ---------------- G-code analysis (Module H) ----------------
def test_gcode_analysis_all_four_sample_files(client, headers_for):
    engineer = headers_for("ENGINEER")
    expectations = {"safe": (True, "NONE"), "malicious_temperature": (False, "HIGH"),
                    "malicious_speed": (False, "HIGH"), "suspicious_command": (False, "HIGH")}
    for name, (safe, risk) in expectations.items():
        response = client.post("/api/manufacturing/analyze-gcode", headers=engineer,
                               files={"file": (f"{name}.gcode", gcode_file(name))})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["safe"] is safe and body["risk"] == risk, (name, body)


def test_malicious_gcode_creates_security_event(client, headers_for):
    engineer = headers_for("ENGINEER")
    client.post("/api/manufacturing/analyze-gcode", headers=engineer,
               files={"file": ("m.gcode", gcode_file("malicious_temperature"))})
    with SessionLocal() as db:
        events = db.execute(select(SecurityEvent).where(
            SecurityEvent.event_type == "MALICIOUS_GCODE_DETECTED")).scalars().all()
    assert events and events[-1].severity == "HIGH"
    logs = client.get("/api/audit/logs", params={"action": "GCODE_ANALYZE", "result": "FAILURE"},
                      headers=headers_for("AUDITOR")).json()
    assert logs["total"] >= 1


def test_gcode_analysis_requires_permission(client, headers_for):
    assert client.post("/api/manufacturing/analyze-gcode", headers=headers_for("VIEWER"),
                       files={"file": ("safe.gcode", gcode_file("safe"))}).status_code == 403


def test_gcode_non_utf8_upload_rejected(client, headers_for):
    response = client.post("/api/manufacturing/analyze-gcode", headers=headers_for("ENGINEER"),
                           files={"file": ("bad.gcode", b"\xff\xfe\x00\x01")})
    assert response.status_code == 422


def test_dashboard_counts_incidents(client, headers_for):
    viewer = headers_for("VIEWER")
    before = client.get("/api/dashboard/summary", headers=viewer).json()["incidents_total"]
    engineer = headers_for("ENGINEER")
    printer_id = get_printer_id(client, engineer)
    stop_all(client, engineer)
    client.post(f"/api/manufacturing/printers/{printer_id}/start", headers=engineer,
               json={"scenario": "SPEED_SPIKE", "seed": 9})

    def has_new_incident():
        after = client.get("/api/dashboard/summary", headers=viewer).json()["incidents_total"]
        return after if after > before else None

    wait_until(has_new_incident, timeout_s=15.0)
    stop_all(client, engineer)
