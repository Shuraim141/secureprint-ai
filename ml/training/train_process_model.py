#!/usr/bin/env python3
"""Train the predictive quality analytics models (Module A3): a RandomForestClassifier for
predicted_quality (good/fair/poor) and an IsolationForest for anomaly_score, over print
process parameters (nozzle/bed temperature, speed, layer height, extrusion rate, duration).

No real production telemetry was supplied with this project; see backend/app/ml/
process_dataset.py for the documented safe-range assumptions this generator uses.

Usage: python ml/training/train_process_model.py [--n-normal 500] [--n-extreme 150]
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np  # noqa: E402
from sklearn.ensemble import IsolationForest, RandomForestClassifier  # noqa: E402
from sklearn.metrics import accuracy_score, precision_recall_fscore_support  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.hardware import get_hardware_profile  # noqa: E402
from app.ml.process_dataset import (  # noqa: E402
    FEATURE_NAMES,
    QUALITY_CLASSES,
    SAFE_RANGES,
    generate_process_dataset,
    to_feature_vector,
)
from app.ml.quality_model import PROCESS_MODEL_FILENAME, ProcessQualityModel  # noqa: E402
from app.models import MLModelMetrics  # noqa: E402
from app.timeutil import iso_utc, utcnow  # noqa: E402

DISCLAIMER = (
    "Metrics are based on the supplied demonstration/synthetic dataset and do not represent "
    "industrial validation."
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-normal", type=int, default=500)
    parser.add_argument("--n-extreme", type=int, default=150)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    settings = get_settings()
    profile = get_hardware_profile(settings.hardware_profile)
    print(f"Hardware profile: {profile.name} (n_estimators={profile.rf_n_estimators})")
    print("Safe operating ranges used to derive labels:")
    for name, (low, high) in SAFE_RANGES.items():
        print(f"  {name:20} [{low}, {high}]")

    values_list, labels, extreme_flags = [], [], []
    for values, label, is_extreme in generate_process_dataset(
            args.n_normal, args.n_extreme, seed=args.seed):
        values_list.append(values)
        labels.append(label)
        extreme_flags.append(is_extreme)
    X = np.array([to_feature_vector(v) for v in values_list])
    y = np.array(labels)
    extreme = np.array(extreme_flags)

    print(f"\nDataset size: {len(X)} ({args.n_normal} normal-regime, {args.n_extreme} extreme-regime)")
    print(f"Label distribution: {{'good': {int((y=='good').sum())}, "
          f"'fair': {int((y=='fair').sum())}, 'poor': {int((y=='poor').sum())}}}")

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.25, random_state=args.seed, stratify=y)
    print(f"Training samples: {len(X_train)}")
    print(f"Validation samples: {len(X_val)}")
    print("Epoch: N/A (Random Forest / Isolation Forest are non-iterative ensemble models)")

    started = time.perf_counter()
    quality_clf = RandomForestClassifier(
        n_estimators=profile.rf_n_estimators, max_depth=10, random_state=args.seed, n_jobs=-1)
    quality_clf.fit(X_train, y_train)
    anomaly_clf = IsolationForest(
        n_estimators=profile.rf_n_estimators, contamination=0.15, random_state=args.seed, n_jobs=-1)
    anomaly_clf.fit(X)  # unsupervised: trained on the full parameter distribution
    train_seconds = time.perf_counter() - started

    predictions = quality_clf.predict(X_val)
    accuracy = accuracy_score(y_val, predictions)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_val, predictions, labels=QUALITY_CLASSES, zero_division=0)
    print(f"\nTraining time: {train_seconds:.2f}s")
    print(f"Quality-prediction accuracy: {accuracy:.4f}")
    per_class = {}
    for cls, p, r, f, s in zip(QUALITY_CLASSES, precision, recall, f1, support, strict=True):
        print(f"  {cls:6} precision={p:.3f} recall={r:.3f} f1={f:.3f} support={int(s)}")
        per_class[cls] = {"precision": round(float(p), 4), "recall": round(float(r), 4),
                          "f1": round(float(f), 4), "support": int(s)}

    iso_pred = anomaly_clf.predict(X)
    extreme_detection_rate = float((iso_pred[extreme] == -1).mean()) if extreme.any() else 0.0
    normal_false_positive_rate = float((iso_pred[~extreme] == -1).mean()) if (~extreme).any() else 0.0
    print(f"\nAnomaly detector: flagged {extreme_detection_rate:.1%} of extreme-regime rows")
    print(f"Anomaly detector: flagged {normal_false_positive_rate:.1%} of normal-regime rows "
          "(false-positive rate)")
    print(f"\n{DISCLAIMER}")

    model_dir = ROOT / "ml" / "models"
    model_path = model_dir / PROCESS_MODEL_FILENAME
    trained_at = iso_utc(utcnow())
    model_version = f"process-rf-iforest-{trained_at[:10]}-{profile.name}"
    model = ProcessQualityModel(quality_clf, anomaly_clf, FEATURE_NAMES, trained_at, model_version)
    model.save(model_path)
    print(f"\nSaved model to {model_path}")

    metrics_payload = {
        "accuracy": round(float(accuracy), 4), "per_class": per_class,
        "extreme_regime_detection_rate": round(extreme_detection_rate, 4),
        "normal_regime_false_positive_rate": round(normal_false_positive_rate, 4),
        "training_seconds": round(train_seconds, 3), "n_estimators": profile.rf_n_estimators,
        "hardware_profile": profile.name, "safe_ranges": {k: list(v) for k, v in SAFE_RANGES.items()},
    }
    init_db()
    with SessionLocal() as db:
        db.add(MLModelMetrics(
            model_name="process_quality", dataset_description=(
                f"Procedurally generated synthetic process-parameter data "
                f"({args.n_normal} normal + {args.n_extreme} extreme regime samples, seed={args.seed}). "
                "NOT real production telemetry."),
            n_train=len(X_train), n_validation=len(X_val), metrics=metrics_payload,
            disclaimer=DISCLAIMER, artifact_path=str(model_path.relative_to(ROOT))))
        db.commit()
    print("Recorded metrics in the database (visible on the Quality Control dashboard).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
