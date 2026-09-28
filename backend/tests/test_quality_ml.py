"""Pure-logic tests for image inspection, feature extraction, dataset generation and the ML
model wrappers. No web framework or database — these run everywhere."""
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from app.cv.inspection import ImageValidationError, decode_image, inspect, preprocess
from app.ml.process_dataset import (
    QUALITY_CLASSES,
    SAFE_RANGES,
    generate_process_dataset,
    to_feature_vector,
)
from app.ml.quality_dataset import CLASSES, generate_dataset, generate_image
from app.ml.quality_features import FEATURE_NAMES, extract_features
from app.ml.quality_model import DefectDetector, ModelNotTrainedError, ProcessQualityModel


def raises(exc_type, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except exc_type as error:
        return error
    raise AssertionError(f"expected {exc_type.__name__}")


def png_bytes(width=32, height=32, fill=128) -> bytes:
    import io
    buf = io.BytesIO()
    Image.new("L", (width, height), color=fill).save(buf, format="PNG")
    return buf.getvalue()


# ---------------- synthetic image dataset ----------------
def test_dataset_generation_is_deterministic_and_covers_all_classes():
    a = generate_image("WARPING", seed=42, size=64)
    b = generate_image("WARPING", seed=42, size=64)
    c = generate_image("WARPING", seed=43, size=64)
    assert a == b and a != c  # same seed -> byte-identical PNG; different seed -> different
    rows = list(generate_dataset(samples_per_class=4, seed=0, size=64))
    assert len(rows) == 4 * len(CLASSES)
    assert {label for label, _ in rows} == set(CLASSES) == {
        "NORMAL", "WARPING", "STRINGING", "LAYER_SHIFT", "CLOGGING"}
    for _, png in rows[:3]:
        decode_image(png)  # every generated image must itself be a valid, decodable PNG


def test_generate_image_rejects_unknown_class():
    raises(ValueError, generate_image, "MELTDOWN", seed=1)


# ---------------- image decoding / hardening ----------------
def test_decode_image_hardening():
    raises(ImageValidationError, decode_image, b"")
    raises(ImageValidationError, decode_image, b"not a real image, just text bytes")
    raises(ImageValidationError, decode_image, png_bytes(8, 8))  # below 16x16 minimum
    array = decode_image(png_bytes(40, 30, fill=200))
    assert array.shape == (30, 40) and array.dtype == np.uint8 and array.mean() == 200


def test_preprocess_resizes_to_target_square():
    array = decode_image(png_bytes(50, 80))
    out = preprocess(array, target_size=32)
    assert out.shape == (32, 32)


# ---------------- CV inspection ----------------
def test_inspect_returns_real_measurements_not_placeholders():
    normal = decode_image(generate_image("NORMAL", seed=1, size=96))
    stringing = decode_image(generate_image("STRINGING", seed=1, size=96))
    report_n, report_s = inspect(normal, 64), inspect(stringing, 64)
    for report in (report_n, report_s):
        assert report["target_size"] == 64
        assert 0.0 <= report["edge_density"] <= 1.0
        assert report["contour_count"] >= 0
        assert len(report["original_png_base64"]) > 100  # a real embedded preview image
        assert len(report["edges_png_base64"]) > 100
    # stringing has many thin random edges -> more contours than a clean NORMAL print
    assert report_s["contour_count"] > report_n["contour_count"]


def test_inspect_flags_low_quality_photos():
    dark = np.full((80, 80), 10, dtype=np.uint8)
    flat = np.full((80, 80), 128, dtype=np.uint8)
    assert any("dark" in w for w in inspect(dark, 64)["quality_flags"])
    assert any("contrast" in w for w in inspect(flat, 64)["quality_flags"])


# ---------------- feature extraction ----------------
def test_feature_vector_shape_and_determinism():
    gray = decode_image(generate_image("CLOGGING", seed=5, size=96))
    f1 = extract_features(gray, 64)
    f2 = extract_features(gray, 64)
    assert f1.shape == (len(FEATURE_NAMES),) and f1.dtype == np.float32
    assert np.array_equal(f1, f2)  # deterministic for identical input
    assert np.isfinite(f1).all()


def test_features_separate_classes_by_hand_computable_margin():
    """Direct evidence the features aren't noise: NORMAL should have high row-line
    regularity, LAYER_SHIFT a large horizontal discontinuity signal — check the exact
    feature index for each, not just 'classifier accuracy is high'."""
    idx = {name: i for i, name in enumerate(FEATURE_NAMES)}
    normal = extract_features(decode_image(generate_image("NORMAL", seed=9, size=96)), 64)
    shifted = extract_features(decode_image(generate_image("LAYER_SHIFT", seed=9, size=96)), 64)
    assert normal[idx["row_line_regularity"]] > shifted[idx["row_line_regularity"]] * 0.5 \
        or shifted[idx["horizontal_discontinuity"]] > normal[idx["horizontal_discontinuity"]]
    assert shifted[idx["horizontal_discontinuity"]] > 0.05


# ---------------- classifier trained end-to-end in this test (real, not mocked) ----------------
def _train_tiny_defect_classifier():
    from sklearn.ensemble import RandomForestClassifier

    X, y = [], []
    for label, png in generate_dataset(samples_per_class=25, seed=3, size=80):
        X.append(extract_features(decode_image(png), 56))
        y.append(label)
    clf = RandomForestClassifier(n_estimators=40, random_state=3, n_jobs=-1)
    clf.fit(np.array(X), np.array(y))
    return DefectDetector(clf, FEATURE_NAMES, CLASSES, "test", "unit-test-v1")


def test_defect_detector_predicts_unseen_images_correctly():
    detector = _train_tiny_defect_classifier()
    correct = 0
    total = 0
    for label in CLASSES:
        gray = decode_image(generate_image(label, seed=99999, size=80))  # unseen seed
        prediction = detector.predict(extract_features(gray, 56))
        total += 1
        correct += prediction.predicted_class == label
        assert abs(sum(prediction.class_probabilities.values()) - 1.0) < 1e-6
        assert 0.0 <= prediction.confidence <= 1.0
    assert correct >= 4  # at least 4/5 unseen classes correct (real generalisation, not memorised)


def test_defect_detector_save_load_roundtrip_and_missing_file():
    detector = _train_tiny_defect_classifier()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "model.joblib"
        detector.save(path)
        reloaded = DefectDetector.load(path)
        assert reloaded.classes == CLASSES and reloaded.model_version == "unit-test-v1"
        gray = decode_image(generate_image("WARPING", seed=1, size=80))
        assert reloaded.predict(extract_features(gray, 56)).predicted_class in CLASSES
        raises(ModelNotTrainedError, DefectDetector.load, Path(tmp) / "missing.joblib")


def test_defect_detector_rejects_wrong_format_version():
    import joblib
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "old.joblib"
        joblib.dump({"format_version": 999}, path)
        raises(ModelNotTrainedError, DefectDetector.load, path)


# ---------------- process-quality dataset and model ----------------
def test_process_dataset_labels_and_safe_ranges():
    rows = list(generate_process_dataset(n_normal=40, n_extreme=10, seed=1))
    assert len(rows) == 50
    labels = {label for _, label, _ in rows}
    assert labels <= set(QUALITY_CLASSES)
    values, _, _ = rows[0]
    vector = to_feature_vector(values)
    assert vector.shape == (len(SAFE_RANGES),)
    # extreme-regime rows should mostly fall outside at least one safe range
    extreme_rows = [v for v, _, is_extreme in rows if is_extreme]
    outside = sum(
        1 for v in extreme_rows
        if any(not (lo <= v[name] <= hi) for name, (lo, hi) in SAFE_RANGES.items() if name != "duration_min")
    )
    assert outside / max(len(extreme_rows), 1) > 0.7


def _train_tiny_process_model():
    from sklearn.ensemble import IsolationForest, RandomForestClassifier

    from app.ml.process_dataset import FEATURE_NAMES as PFN

    X, y = [], []
    for values, label, _ in generate_process_dataset(n_normal=150, n_extreme=50, seed=11):
        X.append(to_feature_vector(values))
        y.append(label)
    X = np.array(X)
    qclf = RandomForestClassifier(n_estimators=40, random_state=11, n_jobs=-1)
    qclf.fit(X, np.array(y))
    iso = IsolationForest(n_estimators=40, contamination=0.15, random_state=11, n_jobs=-1)
    iso.fit(X)
    return ProcessQualityModel(qclf, iso, PFN, "test", "unit-test-process-v1")


def test_process_model_matches_documented_demo_scenario():
    """Exact values from the master specification's Module G example."""
    model = _train_tiny_process_model()
    normal = {"nozzle_temp_c": 205, "bed_temp_c": 60, "speed_mm_s": 50,
              "layer_height_mm": 0.2, "extrusion_rate_pct": 100, "duration_min": 60}
    suspicious = {"nozzle_temp_c": 280, "bed_temp_c": 100, "speed_mm_s": 250,
                  "layer_height_mm": 0.2, "extrusion_rate_pct": 100, "duration_min": 60}
    normal_pred = model.predict(to_feature_vector(normal))
    suspicious_pred = model.predict(to_feature_vector(suspicious))
    assert normal_pred.predicted_quality == "good" and not normal_pred.is_anomaly
    assert normal_pred.risk_level == "LOW"
    assert suspicious_pred.is_anomaly and suspicious_pred.risk_level == "HIGH"
    assert suspicious_pred.predicted_quality in {"fair", "poor"}
    assert suspicious_pred.anomaly_score > normal_pred.anomaly_score


def test_process_model_save_load_roundtrip():
    model = _train_tiny_process_model()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "process.joblib"
        model.save(path)
        reloaded = ProcessQualityModel.load(path)
        assert reloaded.model_version == "unit-test-process-v1"
        pred = reloaded.predict(to_feature_vector(
            {"nozzle_temp_c": 205, "bed_temp_c": 60, "speed_mm_s": 50,
             "layer_height_mm": 0.2, "extrusion_rate_pct": 100, "duration_min": 60}))
        assert abs(sum(pred.quality_probabilities.values()) - 1.0) < 1e-6
        raises(ModelNotTrainedError, ProcessQualityModel.load, Path(tmp) / "missing.joblib")
