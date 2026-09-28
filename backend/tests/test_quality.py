"""AI quality control API: defect detection (image) and predictive analytics (process params)."""
import io

from PIL import Image

from app.ml.quality_dataset import generate_image

NORMAL_PARAMS = {"nozzle_temp_c": 205, "bed_temp_c": 60, "speed_mm_s": 50,
                 "layer_height_mm": 0.2, "extrusion_rate_pct": 100, "duration_min": 60}
SUSPICIOUS_PARAMS = {"nozzle_temp_c": 280, "bed_temp_c": 100, "speed_mm_s": 250,
                     "layer_height_mm": 0.2, "extrusion_rate_pct": 100, "duration_min": 60}


def upload_image(client, headers, label, seed, size=96, filename="print.png"):
    png = generate_image(label, seed=seed, size=size)
    return client.post("/api/quality/inspect", headers=headers,
                       files={"file": (filename, png, "image/png")})


def plain_png(width=8, height=8) -> bytes:
    buf = io.BytesIO()
    Image.new("L", (width, height), color=100).save(buf, format="PNG")
    return buf.getvalue()


# ---------------- access control ----------------
def test_quality_endpoints_require_permission(client, headers_for, trained_models):
    png = generate_image("NORMAL", seed=1)
    assert client.post("/api/quality/inspect",
                       files={"file": ("a.png", png)}).status_code == 401
    for role in ("VIEWER", "SUPPLY_CHAIN", "AUDITOR"):
        assert upload_image(client, headers_for(role), "NORMAL", 1).status_code == 403, role
    assert client.get("/api/quality/history", headers=headers_for("VIEWER")).status_code == 403
    assert client.post("/api/quality/predict", json=NORMAL_PARAMS,
                       headers=headers_for("SUPPLY_CHAIN")).status_code == 200  # QUALITY_VIEW


# ---------------- defect detection ----------------
def test_inspect_normal_and_defective_images(client, headers_for, trained_models):
    inspector = headers_for("QUALITY_INSPECTOR")
    normal = upload_image(client, inspector, "NORMAL", seed=101).json()
    assert normal["status"] == "normal" and normal["defect_type"] == "NORMAL"
    assert 0.0 <= normal["confidence"] <= 1.0
    assert normal["cv_report"]["target_size"] > 0
    assert len(normal["cv_report"]["original_png_base64"]) > 100

    defect = upload_image(client, inspector, "LAYER_SHIFT", seed=202).json()
    assert defect["status"] == "defect_detected"
    assert defect["defect_type"] in {"WARPING", "STRINGING", "LAYER_SHIFT", "CLOGGING"}
    assert defect["severity"] in {"low", "medium", "high"}
    assert set(defect["class_probabilities"]) == {
        "NORMAL", "WARPING", "STRINGING", "LAYER_SHIFT", "CLOGGING"}


def test_inspect_rejects_invalid_images_and_is_audited(client, headers_for, trained_models):
    inspector = headers_for("QUALITY_INSPECTOR")
    bad = client.post("/api/quality/inspect", headers=inspector,
                      files={"file": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 422
    tiny = client.post("/api/quality/inspect", headers=inspector,
                       files={"file": ("x.png", plain_png(4, 4), "image/png")})
    assert tiny.status_code == 422
    logs = client.get("/api/audit/logs", params={"action": "QUALITY_INSPECT_REJECTED"},
                      headers=headers_for("AUDITOR")).json()
    assert logs["total"] >= 2


def test_inspect_oversized_upload(client, headers_for, trained_models):
    huge = b"0" * (2 * 1024 * 1024)  # MAX_UPLOAD_MB=1 in conftest
    response = client.post("/api/quality/inspect", headers=headers_for("QUALITY_INSPECTOR"),
                           files={"file": ("huge.png", huge, "image/png")})
    assert response.status_code == 413


def test_inspection_history_and_lookup(client, headers_for, trained_models):
    inspector = headers_for("QUALITY_INSPECTOR")
    created = upload_image(client, inspector, "STRINGING", seed=303).json()
    history = client.get("/api/quality/history", headers=inspector).json()
    assert history["total"] >= 1
    ids = [row["id"] for row in history["items"]]
    assert created["inspection_id"] in ids
    fetched = client.get(f"/api/quality/history/{created['inspection_id']}", headers=inspector)
    assert fetched.status_code == 200 and fetched.json()["defect_type"] == created["defect_type"]
    assert client.get("/api/quality/history/999999", headers=inspector).status_code == 404


def test_high_severity_defect_creates_security_event(client, headers_for, trained_models):
    inspector = headers_for("QUALITY_INSPECTOR")
    result = None
    for seed in range(400, 420):  # LAYER_SHIFT/CLOGGING map to severity "high"
        candidate = upload_image(client, inspector, "LAYER_SHIFT", seed=seed).json()
        if candidate["severity"] == "high":
            result = candidate
            break
    assert result is not None, "expected at least one high-severity prediction across seeds"
    events = client.get("/api/audit/logs", params={"action": "QUALITY_INSPECT", "limit": 100},
                        headers=headers_for("AUDITOR")).json()
    assert events["total"] >= 1


def test_inspect_returns_503_without_a_trained_model(client, headers_for, monkeypatch, trained_models):
    from app.ml.quality_model import ModelNotTrainedError

    def boom():
        raise ModelNotTrainedError("no model")

    # services/quality.py does `from app.ml.registry import get_defect_detector`, which binds
    # its OWN name in that module's namespace -- patching app.ml.registry.get_defect_detector
    # would not affect the already-imported reference, so we patch it where it is used.
    monkeypatch.setattr("app.services.quality.get_defect_detector", boom)
    response = upload_image(client, headers_for("QUALITY_INSPECTOR"), "NORMAL", seed=1)
    assert response.status_code == 503
    assert "train" in response.json()["detail"].lower()

    from app.ml import registry
    registry.get_defect_detector.cache_clear()  # undo the lru_cache so later tests see the real model


# ---------------- predictive quality analytics ----------------
def test_predict_matches_documented_demo_scenario(client, headers_for, trained_models):
    inspector = headers_for("QUALITY_INSPECTOR")
    normal = client.post("/api/quality/predict", json=NORMAL_PARAMS, headers=inspector).json()
    suspicious = client.post("/api/quality/predict", json=SUSPICIOUS_PARAMS, headers=inspector).json()
    assert normal["predicted_quality"] == "good" and not normal["is_anomaly"]
    assert normal["risk_level"] == "LOW"
    assert suspicious["is_anomaly"] and suspicious["risk_level"] == "HIGH"
    assert suspicious["out_of_range_parameters"]
    assert "nozzle_temp_c" in suspicious["out_of_range_parameters"]
    assert not normal["out_of_range_parameters"]


def test_predict_validation_and_security_event(client, headers_for, trained_models):
    inspector = headers_for("QUALITY_INSPECTOR")
    bad = {**NORMAL_PARAMS, "nozzle_temp_c": -5}
    assert client.post("/api/quality/predict", json=bad, headers=inspector).status_code == 422
    missing = {k: v for k, v in NORMAL_PARAMS.items() if k != "bed_temp_c"}
    assert client.post("/api/quality/predict", json=missing, headers=inspector).status_code == 422

    client.post("/api/quality/predict", json=SUSPICIOUS_PARAMS, headers=inspector)
    events = client.get("/api/audit/logs", params={"action": "QUALITY_PREDICT"},
                        headers=headers_for("AUDITOR")).json()
    assert events["total"] >= 1


# ---------------- model metrics ----------------
def test_model_metrics_endpoint(client, headers_for, trained_models):
    assert client.get("/api/quality/models/nonsense",
                      headers=headers_for("QUALITY_INSPECTOR")).status_code == 404
    # trained_models fixture trains models in-process but does not write MLModelMetrics rows
    # (that only happens via the real training scripts), so an untrained-metrics lookup 404s:
    response = client.get("/api/quality/models/defect_detector",
                          headers=headers_for("QUALITY_INSPECTOR"))
    assert response.status_code == 404
    assert "training" in response.json()["detail"].lower()


def test_health_reports_ml_ok_once_models_are_trained(client, trained_models):
    body = client.get("/health").json()
    assert body["ml"] == "ok"


def test_dashboard_counts_defects(client, headers_for, trained_models):
    viewer = headers_for("VIEWER")
    before = client.get("/api/dashboard/summary", headers=viewer).json()["defects_detected"]
    inspector = headers_for("QUALITY_INSPECTOR")
    for seed in range(500, 520):
        result = upload_image(client, inspector, "CLOGGING", seed=seed).json()
        if result["status"] == "defect_detected":
            break
    after = client.get("/api/dashboard/summary", headers=viewer).json()["defects_detected"]
    assert after > before
