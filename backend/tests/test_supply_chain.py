"""Supply-chain provenance and part authentication API (Modules D/E)."""
from sqlalchemy import select

from app.blockchain.workflow import WORKFLOW_STEPS
from app.database import SessionLocal
from app.models import SupplyChainEvent

_counter = iter(range(1, 100_000))


def register_design(client, headers):
    """Register a fresh design. Y/Z (33 x 13 mm) differ from test_designs.py's models (30 x 10),
    so the two modules can never produce byte-identical files: the registry rejects exact
    duplicates with 409, and both modules share one session-scoped test database."""
    from app.geometry import samples
    width = 50.0 + next(_counter)
    data = samples.write_binary_stl(samples.make_box((width, 33.0, 13.0), (8, 4, 2)))
    response = client.post("/api/designs", headers=headers, files={"file": ("p.stl", data)})
    assert response.status_code == 201, response.text
    return response.json()


def create_part(client, headers, design_id, batch="BATCH-001", material="PLA"):
    return client.post("/api/supply-chain/parts", headers=headers,
                       json={"design_id": design_id, "batch": batch, "material": material})


def advance_to(client, headers, part_id, action):
    """Append every event from DESIGN_APPROVED up to and including `action` (skips
    DESIGN_CREATED, which create_part already seeded)."""
    last = None
    for step in WORKFLOW_STEPS[1:]:  # DESIGN_APPROVED, SLICED, ...
        response = client.post(f"/api/supply-chain/parts/{part_id}/events",
                               headers=headers, json={"action": step})
        assert response.status_code == 201, response.text
        last = response.json()
        if step == action:
            return last
    return last


# ---------------- access control ----------------
def test_supply_chain_requires_permission(client, headers_for):
    design = register_design(client, headers_for("ENGINEER"))
    for role in ("VIEWER", "AUDITOR"):  # neither role has provenance:create
        assert create_part(client, headers_for(role), design["id"]).status_code == 403, role
    for role in ("QUALITY_INSPECTOR", "SUPPLY_CHAIN"):  # both do, per the RBAC matrix
        assert create_part(client, headers_for(role), design["id"]).status_code == 201, role
    created = create_part(client, headers_for("SUPPLY_CHAIN"), design["id"])
    assert created.status_code == 201
    assert client.get("/api/supply-chain/parts", headers=headers_for("VIEWER")).status_code == 200
    assert client.get(f"/api/supply-chain/authenticate/{created.json()['part_code']}",
                      headers=headers_for("VIEWER")).status_code == 200


# ---------------- part creation seeds DESIGN_CREATED ----------------
def test_create_part_seeds_design_created_event(client, headers_for):
    engineer = headers_for("ENGINEER")
    design = register_design(client, engineer)
    part = create_part(client, engineer, design["id"], batch="B1", material="PETG").json()
    assert part["part_code"].startswith("PART-")
    assert part["design_code"] == design["design_code"]
    assert part["design_hash"] == design["sha256"]
    assert part["status"] == "DESIGN_CREATED"

    detail = client.get(f"/api/supply-chain/parts/{part['id']}", headers=engineer).json()
    assert len(detail["events"]) == 1
    assert detail["events"][0]["action"] == "DESIGN_CREATED"
    assert detail["chain_verification"]["valid"] is True
    assert len(detail["events"][0]["signature"]) == 128


def test_part_requires_existing_design_with_a_version(client, headers_for):
    engineer = headers_for("ENGINEER")
    assert create_part(client, engineer, design_id=999999).status_code == 404


# ---------------- workflow order enforcement ----------------
def test_workflow_order_is_enforced_via_api(client, headers_for):
    engineer = headers_for("ENGINEER")
    design = register_design(client, engineer)
    part = create_part(client, engineer, design["id"]).json()
    pid = part["id"]

    # skipping ahead (DESIGN_CREATED already happened; try SHIPPED next) must fail
    out_of_order = client.post(f"/api/supply-chain/parts/{pid}/events",
                               headers=engineer, json={"action": "SHIPPED"})
    assert out_of_order.status_code == 409
    assert "expected" in out_of_order.json()["detail"].lower()

    # correct next step succeeds
    ok = client.post(f"/api/supply-chain/parts/{pid}/events",
                     headers=engineer, json={"action": "DESIGN_APPROVED"})
    assert ok.status_code == 201 and ok.json()["sequence"] == 2

    # repeating a completed step fails
    repeat = client.post(f"/api/supply-chain/parts/{pid}/events",
                         headers=engineer, json={"action": "DESIGN_APPROVED"})
    assert repeat.status_code == 409

    rejected = client.get("/api/audit/logs", params={"action": "PROVENANCE_EVENT_REJECTED"},
                          headers=headers_for("AUDITOR")).json()
    assert rejected["total"] >= 2


def test_full_workflow_to_received_and_part_status_updates(client, headers_for):
    engineer = headers_for("ENGINEER")
    design = register_design(client, engineer)
    part = create_part(client, engineer, design["id"]).json()
    final = advance_to(client, headers_for("SUPPLY_CHAIN"), part["id"], "RECEIVED")
    assert final["action"] == "RECEIVED" and final["sequence"] == 9

    detail = client.get(f"/api/supply-chain/parts/{part['id']}", headers=engineer).json()
    assert [e["action"] for e in detail["events"]] == list(WORKFLOW_STEPS)
    assert detail["part"]["status"] == "RECEIVED"
    assert detail["chain_verification"]["valid"] is True

    verify = client.get(f"/api/supply-chain/parts/{part['id']}/verify", headers=engineer).json()
    assert verify["valid"] is True and verify["checked"] == 9


# ---------------- part authentication ----------------
def test_authenticate_unknown_authentic_and_tampered(client, headers_for):
    viewer = headers_for("VIEWER")
    unknown = client.get("/api/supply-chain/authenticate/PART-999999", headers=viewer).json()
    assert unknown["verdict"] == "UNKNOWN" and unknown["part"] is None

    engineer = headers_for("ENGINEER")
    design = register_design(client, engineer)
    part = create_part(client, engineer, design["id"]).json()
    authentic = client.get(f"/api/supply-chain/authenticate/{part['part_code']}",
                           headers=viewer).json()
    assert authentic["verdict"] == "AUTHENTIC"
    assert authentic["part"]["part_code"] == part["part_code"]
    assert authentic["chain_verification"]["valid"] is True

    # DEMO 5 from the spec: modify an earlier ledger event directly in the database
    with SessionLocal() as db:
        row = db.execute(select(SupplyChainEvent).where(
            SupplyChainEvent.chain_id == part["part_code"],
            SupplyChainEvent.sequence == 1)).scalar_one()
        original_actor = row.actor
        row.actor = "attacker"
        db.commit()
    try:
        tampered = client.get(f"/api/supply-chain/authenticate/{part['part_code']}",
                              headers=viewer).json()
        assert tampered["verdict"] == "TAMPERED"
        assert "#1" in tampered["reason"] or "event #1" in tampered["reason"].lower()
        assert tampered["chain_verification"]["valid"] is False
        assert tampered["chain_verification"]["first_broken_event"] == 1

        verify_endpoint = client.get(f"/api/supply-chain/parts/{part['id']}/verify",
                                     headers=engineer).json()
        assert verify_endpoint["valid"] is False and verify_endpoint["first_broken_event"] == 1
    finally:
        with SessionLocal() as db:
            row = db.execute(select(SupplyChainEvent).where(
                SupplyChainEvent.chain_id == part["part_code"],
                SupplyChainEvent.sequence == 1)).scalar_one()
            row.actor = original_actor
            db.commit()
    restored = client.get(f"/api/supply-chain/authenticate/{part['part_code']}",
                          headers=viewer).json()
    assert restored["verdict"] == "AUTHENTIC"


def test_tamper_creates_security_event_and_is_audited(client, headers_for):
    engineer = headers_for("ENGINEER")
    design = register_design(client, engineer)
    part = create_part(client, engineer, design["id"]).json()
    with SessionLocal() as db:
        row = db.execute(select(SupplyChainEvent).where(
            SupplyChainEvent.chain_id == part["part_code"])).scalar_one()
        row.action = "TAMPERED_ACTION"
        db.commit()
    try:
        client.get(f"/api/supply-chain/authenticate/{part['part_code']}", headers=engineer)
        from app.models import SecurityEvent
        with SessionLocal() as db:
            events = db.execute(select(SecurityEvent).where(
                SecurityEvent.event_type == "PART_AUTHENTICATION_TAMPERED",
                SecurityEvent.resource == f"part:{part['part_code']}")).scalars().all()
        assert events and events[0].severity == "HIGH"
        logs = client.get("/api/audit/logs", params={"action": "PART_AUTHENTICATE",
                                                      "result": "FAILURE"},
                          headers=headers_for("AUDITOR")).json()
        assert logs["total"] >= 1
    finally:
        with SessionLocal() as db:
            row = db.execute(select(SupplyChainEvent).where(
                SupplyChainEvent.chain_id == part["part_code"])).scalar_one()
            row.action = "DESIGN_CREATED"
            db.commit()


def test_dashboard_counts_parts_and_events(client, headers_for):
    viewer = headers_for("VIEWER")
    before = client.get("/api/dashboard/summary", headers=viewer).json()
    engineer = headers_for("ENGINEER")
    design = register_design(client, engineer)
    create_part(client, engineer, design["id"])
    after = client.get("/api/dashboard/summary", headers=viewer).json()
    assert after["parts"] == before["parts"] + 1
    assert after["supply_chain_events"] == before["supply_chain_events"] + 1
