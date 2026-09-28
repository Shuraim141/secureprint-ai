"""3D/4D design security API: registration, analysis, encryption, verification, tampering."""
import hashlib
import io
import re
import zipfile

import numpy as np
from conftest import PASSWORD
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.geometry import samples
from app.geometry.analysis import geometric_fingerprint
from app.geometry.parsers import parse_mesh
from app.models import Design4DProfile, DesignVersion, SecurityEvent

_counter = iter(range(1, 100_000))


def unique_model():
    """A fresh watertight box (224 triangles) whose size, hash and fingerprint are unique."""
    width = 50.0 + next(_counter)
    triangles = samples.make_box((width, 30.0, 10.0), (8, 4, 2))
    return width, triangles, samples.write_binary_stl(triangles)


def upload(client, headers, data, filename="part.stl", name=None):
    return client.post("/api/designs", headers=headers, data={"name": name} if name else {},
                       files={"file": (filename, data, "application/octet-stream")})


def verify(client, headers, data, filename="check.stl", design_id=None):
    form = {"design_id": str(design_id)} if design_id is not None else {}
    return client.post("/api/designs/verify", headers=headers, data=form,
                       files={"file": (filename, data, "application/octet-stream")})


def login_headers(client, make_user, username, role):
    make_user(username, role)
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def storage_path(sha256):
    with SessionLocal() as db:
        key = db.execute(select(DesignVersion.storage_key)
                         .where(DesignVersion.sha256 == sha256)).scalar_one()
    return get_settings().storage_dir / "designs" / key


def audit_actions(client, headers_for, **params):
    logs = client.get("/api/audit/logs", params={"limit": 500, **params},
                      headers=headers_for("AUDITOR")).json()
    return logs["items"]


# ---------------------------------------------------------------- access control
def test_design_endpoints_require_authentication_and_permission(client, headers_for):
    _, _, data = unique_model()
    assert client.post("/api/designs", files={"file": ("a.stl", data)}).status_code == 401
    assert client.get("/api/designs").status_code == 401
    for role in ("VIEWER", "QUALITY_INSPECTOR", "SUPPLY_CHAIN", "AUDITOR"):
        assert upload(client, headers_for(role), data).status_code == 403, role
    for role in ("VIEWER",):
        assert verify(client, headers_for(role), data).status_code == 403
    assert verify(client, headers_for("AUDITOR"), data).status_code == 200


# ---------------------------------------------------------------- registration and analysis
def test_register_returns_real_analysis_and_fingerprints(client, headers_for):
    width, triangles, data = unique_model()
    response = upload(client, headers_for("ENGINEER"), data, "bracket.stl", name="Test Bracket")
    assert response.status_code == 201, response.text
    body = response.json()
    assert re.fullmatch(r"SP-3D-\d{6}", body["design_code"])
    assert body["name"] == "Test Bracket" and body["current_version"] == 1 and body["is_4d"] is False
    version = body["versions"][0]
    assert version["sha256"] == hashlib.sha256(data).hexdigest()
    assert version["file_size"] == len(data)
    analysis = version["analysis"]
    assert analysis["triangle_count"] == 224 and analysis["vertex_count"] == 114
    assert analysis["dimensions_mm"] == {"x": width, "y": 30.0, "z": 10.0}
    assert abs(analysis["volume_mm3"] - width * 300.0) < 0.01
    assert analysis["watertight"] is True and analysis["format"] == "stl"
    assert version["encrypted"] is True and version["encryption_alg"] == "AES-256-GCM"
    fingerprints = {f["kind"]: f for f in version["fingerprints"]}
    assert set(fingerprints) == {"sha256", "geometric", "watermark"}
    assert fingerprints["geometric"]["value"] == geometric_fingerprint(triangles)
    assert fingerprints["watermark"]["meta"]["status"] == "applied"
    assert fingerprints["watermark"]["meta"]["max_abs_change"] < 1e-4
    assert body["history"][0]["event"] == "DESIGN_REGISTERED"


def test_stored_file_is_encrypted_on_disk(client, headers_for):
    _, _, data = unique_model()
    upload(client, headers_for("ENGINEER"), data)
    stored = storage_path(hashlib.sha256(data).hexdigest()).read_bytes()
    assert stored != data and len(stored) == len(data) + 16  # ciphertext + GCM tag
    assert b"SecurePrint AI demo model" not in stored and data[84:200] not in stored


def test_duplicate_file_is_rejected_even_from_another_user(client, headers_for):
    _, _, data = unique_model()
    first = upload(client, headers_for("ENGINEER"), data).json()
    again = upload(client, headers_for("ADMIN"), data)
    assert again.status_code == 409 and first["design_code"] in again.json()["detail"]


def test_ownership_isolation(client, headers_for, make_user):
    _, _, data = unique_model()
    mine = headers_for("ENGINEER")
    other = login_headers(client, make_user, "eng_two", "ENGINEER")
    design = upload(client, mine, data).json()
    base = f"/api/designs/{design['id']}"
    assert client.get(base, headers=other).status_code == 404
    assert client.get(f"{base}/versions/1/download", headers=other).status_code == 404
    assert client.put(f"{base}/4d", headers=other, json={}).status_code in (404, 422)
    assert design["id"] not in [d["id"] for d in client.get("/api/designs", headers=other).json()]
    assert client.get(base, headers=headers_for("ADMIN")).status_code == 200
    denied = audit_actions(client, headers_for, action="DESIGN_ACCESS_DENIED", user="eng_two")
    assert any(design["design_code"] in (row["resource"] or "") for row in denied)


def test_download_decrypts_original_and_is_audited(client, headers_for):
    _, _, data = unique_model()
    design = upload(client, headers_for("ENGINEER"), data, "exact.stl").json()
    url = f"/api/designs/{design['id']}/versions/1/download"
    response = client.get(url, headers=headers_for("ENGINEER"))
    assert response.status_code == 200 and response.content == data
    assert 'filename="exact.stl"' in response.headers["content-disposition"]
    assert client.get(url, headers=headers_for("VIEWER")).status_code == 403
    assert client.get(url, headers=headers_for("QUALITY_INSPECTOR")).status_code == 403
    rows = audit_actions(client, headers_for, action="DESIGN_DOWNLOAD", user="t_engineer")
    assert any(design["design_code"] in (r["resource"] or "") for r in rows)


def test_audit_trail_records_registration_and_encryption(client, headers_for):
    _, _, data = unique_model()
    design = upload(client, headers_for("ENGINEER"), data).json()
    for action in ("DESIGN_REGISTER", "DESIGN_ENCRYPT"):
        rows = audit_actions(client, headers_for, action=action, user="t_engineer")
        assert any(design["design_code"] in (r["resource"] or "") for r in rows), action


# ---------------------------------------------------------------- verification
def test_verify_authentic_then_tampered(client, headers_for):
    width, triangles, data = unique_model()
    eng = headers_for("ENGINEER")
    design = upload(client, eng, data).json()

    ok = verify(client, eng, data, design_id=design["id"]).json()
    assert ok["verdict"] == "AUTHENTIC" and ok["checks"]["sha256_match"] is True
    assert ok["matched_design"]["design_code"] == design["design_code"]

    tampered = samples.write_binary_stl(samples.tamper_mesh(triangles, 0.5))
    bad = verify(client, eng, tampered, design_id=design["id"]).json()
    assert bad["verdict"] == "TAMPERED" and "MISMATCH" in bad["headline"].upper()
    assert bad["checks"]["sha256_match"] is False and bad["checks"]["geometric_match"] is False
    changes = bad["differences"]
    assert "volume_mm3" in changes["changed"] and "dimension_x_mm" in changes["changed"]
    assert abs(changes["metrics"]["volume_mm3"]["delta"] - 150.0) < 0.01
    assert changes["metrics"]["triangle_count"]["changed"] is False

    with SessionLocal() as db:
        events = db.execute(select(SecurityEvent).where(
            SecurityEvent.event_type == "DESIGN_TAMPER_DETECTED",
            SecurityEvent.resource == f"design:{design['design_code']}")).scalars().all()
    assert events and events[0].severity == "HIGH" and events[0].event_code.startswith("EVT-")
    rows = audit_actions(client, headers_for, action="DESIGN_VERIFY", result="FAILURE")
    assert any(r["severity"] == "HIGH" for r in rows)

    other = verify(client, headers_for("QUALITY_INSPECTOR"), tampered, design_id=design["id"]).json()
    assert other["verdict"] == "TAMPERED" and other["differences"] is None  # not the owner


def test_verify_recognises_reexports_as_geometry_match(client, headers_for):
    _, triangles, data = unique_model()
    eng = headers_for("ENGINEER")
    design = upload(client, eng, data).json()
    shuffled = triangles[np.random.default_rng(3).permutation(len(triangles))][:, [1, 2, 0], :]
    for filename, blob in [("copy.stl", samples.write_ascii_stl(triangles)),
                           ("copy.obj", samples.write_obj(triangles)),
                           ("copy.3mf", samples.write_3mf(triangles)),
                           ("shuffled.stl", samples.write_binary_stl(shuffled))]:
        result = verify(client, eng, blob, filename).json()
        assert result["verdict"] == "GEOMETRY_MATCH", (filename, result)
        assert result["matched_design"]["design_code"] == design["design_code"]


def test_verify_unregistered_invalid_and_unsupported(client, headers_for):
    eng = headers_for("ENGINEER")
    _, _, data = unique_model()
    assert verify(client, eng, data).json()["verdict"] == "UNREGISTERED"
    broken = verify(client, eng, b"this is definitely not a model", "x.stl")
    assert broken.status_code == 200 and broken.json()["verdict"] == "INVALID_FILE"
    assert verify(client, eng, data, "x.exe").status_code == 415
    assert verify(client, eng, data, design_id=99999).status_code == 404


def test_verify_against_wrong_design(client, headers_for):
    eng = headers_for("ENGINEER")
    _, _, data_a = unique_model()
    _, _, data_b = unique_model()
    design_a, design_b = upload(client, eng, data_a).json(), upload(client, eng, data_b).json()
    result = verify(client, eng, data_a, design_id=design_b["id"]).json()
    assert result["verdict"] == "WRONG_DESIGN"
    assert result["matched_design"]["design_code"] == design_a["design_code"]


# ---------------------------------------------------------------- watermark
def test_watermarked_copy_authentic_and_edited_copy_traced(client, headers_for):
    _, _, data = unique_model()
    eng = headers_for("ENGINEER")
    design = upload(client, eng, data).json()
    meta = {f["kind"]: f for f in design["versions"][0]["fingerprints"]}["watermark"]["meta"]

    response = client.get(f"/api/designs/{design['id']}/versions/1/watermarked", headers=eng)
    assert response.status_code == 200
    copy = response.content
    assert hashlib.sha256(copy).hexdigest() == meta["distribution_sha256"]
    assert copy != data  # different bytes, invisible geometric difference

    authentic = verify(client, eng, copy).json()
    assert authentic["verdict"] == "AUTHENTIC" and authentic["match_type"] == "watermarked_copy"

    edited = samples.write_binary_stl(samples.tamper_mesh(parse_mesh(copy, "stl"), 0.5))
    traced = verify(client, eng, edited).json()
    assert traced["verdict"] == "TAMPERED"
    assert traced["matched_design"]["design_code"] == design["design_code"]
    assert traced["checks"]["watermark"]["detected"] is True
    assert traced["differences"] is not None


# ---------------------------------------------------------------- upload hardening
def test_invalid_uploads_are_rejected_and_audited(client, headers_for):
    eng = headers_for("ENGINEER")
    _, _, data = unique_model()
    assert upload(client, eng, data, "virus.exe").status_code == 415
    assert upload(client, eng, b"hello, not a model", "fake.stl").status_code == 422
    poisoned = samples.make_box().copy()
    poisoned[0, 0, 0] = np.nan
    assert upload(client, eng, samples.write_binary_stl(poisoned), "nan.stl").status_code == 422
    xxe = (b'<?xml version="1.0"?><!DOCTYPE m [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
           b'<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">&x;</model>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("3D/3dmodel.model", xxe)
    assert upload(client, eng, buffer.getvalue(), "xxe.3mf").status_code == 422
    rejected = audit_actions(client, headers_for, action="DESIGN_UPLOAD_REJECTED")
    assert len(rejected) >= 4


def test_oversized_uploads_get_413(client, headers_for):
    eng = headers_for("ENGINEER")  # MAX_UPLOAD_MB=1 in conftest
    assert upload(client, eng, b"0" * int(1.5 * 1024 * 1024), "big.stl").status_code == 413
    assert upload(client, eng, b"0" * (3 * 1024 * 1024), "huge.stl").status_code == 413


def test_path_traversal_filename_cannot_escape_storage(client, headers_for):
    _, _, data = unique_model()
    response = upload(client, headers_for("ENGINEER"), data, "../../evil.stl")
    assert response.status_code == 201
    assert response.json()["versions"][0]["original_filename"] == "evil.stl"
    root = get_settings().storage_dir
    stored = [p for p in (root / "designs").iterdir() if p.is_file()]
    assert stored and all(re.fullmatch(r"[a-f0-9]{32}\.enc", p.name) for p in stored)
    assert not list(root.parent.rglob("evil.stl"))


# ---------------------------------------------------------------- integrity of stored data
def test_tampered_ciphertext_is_detected_on_download(client, headers_for):
    _, _, data = unique_model()
    eng = headers_for("ENGINEER")
    design = upload(client, eng, data).json()
    path = storage_path(hashlib.sha256(data).hexdigest())
    raw = bytearray(path.read_bytes())
    raw[20] ^= 0xFF
    path.write_bytes(bytes(raw))
    response = client.get(f"/api/designs/{design['id']}/versions/1/download", headers=eng)
    assert response.status_code == 409 and "integrity" in response.json()["detail"].lower()
    with SessionLocal() as db:
        events = db.execute(select(SecurityEvent).where(
            SecurityEvent.event_type == "STORAGE_INTEGRITY_FAILURE",
            SecurityEvent.resource == f"design:{design['design_code']}")).scalars().all()
    assert events and events[0].severity == "HIGH"


def test_new_version_and_history(client, headers_for):
    _, _, data1 = unique_model()
    _, _, data2 = unique_model()
    eng = headers_for("ENGINEER")
    design = upload(client, eng, data1).json()
    url = f"/api/designs/{design['id']}/versions"
    added = client.post(url, headers=eng, files={"file": ("v2.stl", data2)})
    assert added.status_code == 201, added.text
    body = added.json()
    assert body["current_version"] == 2 and [v["version"] for v in body["versions"]] == [1, 2]
    assert [e["event"] for e in body["history"]] == ["DESIGN_REGISTERED", "VERSION_ADDED"]
    assert client.post(url, headers=eng, files={"file": ("dup.stl", data1)}).status_code == 409
    for number, expected in ((1, data1), (2, data2)):
        got = client.get(f"{url}/{number}/download", headers=eng)
        assert got.content == expected
    assert client.get(f"{url}/9/download", headers=eng).status_code == 404


def test_dashboard_counts_registered_designs(client, headers_for):
    viewer = headers_for("VIEWER")
    before = client.get("/api/dashboard/summary", headers=viewer).json()["designs"]
    _, _, data = unique_model()
    upload(client, headers_for("ENGINEER"), data)
    assert client.get("/api/dashboard/summary", headers=viewer).json()["designs"] == before + 1


# ---------------------------------------------------------------- 4D metadata
PROFILE = {
    "material_id": "SMP-PLA-01", "material_name": "Shape-memory PLA",
    "material_class": "shape-memory polymer", "trigger_type": "temperature",
    "trigger_temperature_c": 60, "trigger_time_s": 30, "target_state": "folded",
    "transformation_profile": {"shape_recovery_ratio": 0.95},
    "activation_conditions": {"min_hold_seconds": 30},
}


def test_4d_profile_lifecycle_and_tamper_detection(client, headers_for, make_user):
    _, _, data = unique_model()
    eng = headers_for("ENGINEER")
    design = upload(client, eng, data).json()
    base = f"/api/designs/{design['id']}"

    saved = client.put(f"{base}/4d", headers=eng, json=PROFILE)
    assert saved.status_code == 200, saved.text
    assert re.fullmatch(r"[a-f0-9]{64}", saved.json()["security_fingerprint"])
    assert saved.json()["design_version"] == 1 and saved.json()["target_state"] == "folded"
    detail = client.get(base, headers=eng).json()
    assert detail["is_4d"] is True and detail["profile_4d"]["trigger_temperature_c"] == 60.0
    assert any(e["event"] == "4D_PROFILE_SET" for e in detail["history"])
    assert client.post(f"{base}/4d/verify", headers=eng).json()["intact"] is True

    with SessionLocal() as db:  # attacker edits the database row directly
        row = db.execute(select(Design4DProfile).where(
            Design4DProfile.design_id == design["id"])).scalar_one()
        row.trigger_temperature_c = 95.0
        db.commit()
    tampered = client.post(f"{base}/4d/verify", headers=eng).json()
    assert tampered["intact"] is False and tampered["expected"] != tampered["stored"]
    with SessionLocal() as db:
        assert db.execute(select(SecurityEvent).where(
            SecurityEvent.event_type == "4D_PROFILE_TAMPER_DETECTED",
            SecurityEvent.resource == f"design:{design['design_code']}")).first()
        row = db.execute(select(Design4DProfile).where(
            Design4DProfile.design_id == design["id"])).scalar_one()
        row.trigger_temperature_c = 60.0
        db.commit()
    assert client.post(f"{base}/4d/verify", headers=eng).json()["intact"] is True


def test_4d_profile_validation_and_ownership(client, headers_for, make_user):
    _, _, data = unique_model()
    eng = headers_for("ENGINEER")
    design = upload(client, eng, data).json()
    url = f"/api/designs/{design['id']}/4d"
    no_temp = {**PROFILE, "trigger_temperature_c": None}
    assert client.put(url, headers=eng, json=no_temp).status_code == 422
    assert client.put(url, headers=eng, json={**PROFILE, "trigger_type": "telepathy"}).status_code == 422
    assert client.put(url, headers=eng, json={**PROFILE, "trigger_time_s": -5}).status_code == 422
    huge = {**PROFILE, "transformation_profile": {"x": "y" * 5000}}
    assert client.put(url, headers=eng, json=huge).status_code == 422
    assert client.get(url, headers=eng).status_code == 404  # none saved yet
    other = login_headers(client, make_user, "eng_three", "ENGINEER")
    assert client.put(url, headers=other, json=PROFILE).status_code == 404
    assert client.put(url, headers=headers_for("VIEWER"), json=PROFILE).status_code == 403
