#!/usr/bin/env python3
"""Train the classical CV + Random Forest defect classifier (Module A1/A2).

Trains on procedurally generated synthetic images by default (see backend/app/ml/
quality_dataset.py). Point --data-dir at real labelled photos instead if you have them:
expected layout <data-dir>/<CLASS_NAME>/*.png (or .jpg), CLASS_NAME one of NORMAL, WARPING,
STRINGING, LAYER_SHIFT, CLOGGING.

Usage:
  python ml/training/train_defect_model.py
  python ml/training/train_defect_model.py --samples-per-class 200
  python ml/training/train_defect_model.py --data-dir /path/to/real/photos

Training does NOT run automatically at application startup (see backend/app/main.py); this
script is the only way a model gets (re)trained.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.cv.inspection import ImageValidationError, decode_image  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.hardware import get_hardware_profile  # noqa: E402
from app.ml.quality_dataset import CLASSES, generate_dataset  # noqa: E402
from app.ml.quality_features import FEATURE_NAMES, extract_features  # noqa: E402
from app.ml.quality_model import DEFECT_MODEL_FILENAME, DefectDetector  # noqa: E402
from app.models import MLModelMetrics  # noqa: E402
from app.timeutil import iso_utc, utcnow  # noqa: E402

DISCLAIMER = (
    "Metrics are based on the supplied demonstration/synthetic dataset and do not represent "
    "industrial validation."
)


def load_from_directory(data_dir: Path):
    for class_dir in sorted(data_dir.iterdir()):
        if not class_dir.is_dir() or class_dir.name not in CLASSES:
            continue
        for image_path in sorted(class_dir.glob("*")):
            if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                continue
            yield class_dir.name, image_path.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-per-class", type=int, default=None,
                        help="Synthetic images per class (default: from hardware profile)")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="Real photos instead of synthetic data (see docstring for layout)")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    settings = get_settings()
    profile = get_hardware_profile(settings.hardware_profile)
    image_size = profile.ml_image_size
    n_estimators = profile.rf_n_estimators
    samples_per_class = args.samples_per_class or profile.max_training_samples_per_class

    print(f"Hardware profile: {profile.name} (image_size={image_size}, "
          f"n_estimators={n_estimators}, samples_per_class={samples_per_class})")

    labels, images = [], []
    if args.data_dir:
        print(f"Loading real images from {args.data_dir}")
        for label, data in load_from_directory(args.data_dir):
            labels.append(label)
            images.append(data)
        dataset_description = f"Real images supplied at {args.data_dir}"
    else:
        print(f"Generating synthetic dataset: {samples_per_class} images x {len(CLASSES)} classes")
        for label, png in generate_dataset(samples_per_class, seed=args.seed, size=image_size * 2):
            labels.append(label)
            images.append(png)
        dataset_description = (
            f"Procedurally generated synthetic images ({samples_per_class}/class, seed={args.seed}). "
            "NOT real print-defect photographs."
        )

    print(f"Dataset size: {len(images)}")
    if len(images) < 20:
        print("ERROR: too few samples to train/evaluate meaningfully.")
        return 1

    print("Extracting features (OpenCV)...")
    features, kept_labels, skipped = [], [], 0
    for label, data in zip(labels, images, strict=True):
        try:
            gray = decode_image(data)
        except ImageValidationError as exc:
            skipped += 1
            print(f"  skipping unreadable image ({label}): {exc}")
            continue
        features.append(extract_features(gray, image_size))
        kept_labels.append(label)
    if skipped:
        print(f"Skipped {skipped} unreadable image(s)")
    X = np.asarray(features)
    y = np.asarray(kept_labels)

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.25, random_state=args.seed, stratify=y)
    print(f"Training samples: {len(X_train)}")
    print(f"Validation samples: {len(X_val)}")
    print("Epoch: N/A (Random Forest is a non-iterative ensemble model, not trained by epoch)")

    started = time.perf_counter()
    classifier = RandomForestClassifier(
        n_estimators=n_estimators, max_depth=12, random_state=args.seed, n_jobs=-1)
    classifier.fit(X_train, y_train)
    train_seconds = time.perf_counter() - started

    predictions = classifier.predict(X_val)
    accuracy = accuracy_score(y_val, predictions)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_val, predictions, labels=CLASSES, zero_division=0)
    matrix = confusion_matrix(y_val, predictions, labels=CLASSES)

    print(f"\nTraining time: {train_seconds:.2f}s")
    print(f"Accuracy: {accuracy:.4f}")
    per_class = {}
    for cls, p, r, f, s in zip(CLASSES, precision, recall, f1, support, strict=True):
        print(f"  {cls:12} precision={p:.3f} recall={r:.3f} f1={f:.3f} support={int(s)}")
        per_class[cls] = {"precision": round(float(p), 4), "recall": round(float(r), 4),
                          "f1": round(float(f), 4), "support": int(s)}
    print("\nConfusion matrix (rows=true, cols=predicted):", CLASSES)
    print(matrix)
    print(f"\n{DISCLAIMER}")

    model_dir = ROOT / "ml" / "models"
    model_path = model_dir / DEFECT_MODEL_FILENAME
    trained_at = iso_utc(utcnow())
    model_version = f"defect-rf-{trained_at[:10]}-{profile.name}"
    detector = DefectDetector(classifier, FEATURE_NAMES, CLASSES, trained_at, model_version)
    detector.save(model_path)
    print(f"\nSaved model to {model_path}")

    metrics_payload = {
        "accuracy": round(float(accuracy), 4), "per_class": per_class,
        "confusion_matrix": matrix.tolist(), "confusion_matrix_labels": CLASSES,
        "training_seconds": round(train_seconds, 3), "n_estimators": n_estimators,
        "image_size": image_size, "hardware_profile": profile.name,
    }
    init_db()
    with SessionLocal() as db:
        db.add(MLModelMetrics(
            model_name="defect_detector", dataset_description=dataset_description,
            n_train=len(X_train), n_validation=len(X_val), metrics=metrics_payload,
            disclaimer=DISCLAIMER, artifact_path=str(model_path.relative_to(ROOT))))
        db.commit()
    print("Recorded metrics in the database (visible on the Quality Control dashboard).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
