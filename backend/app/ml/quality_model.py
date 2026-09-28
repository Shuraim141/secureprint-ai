"""Model wrappers: DefectDetector (image -> class) and ProcessQualityModel (process
parameters -> predicted quality + anomaly score). Both are scikit-learn Random
Forest / Isolation Forest, loaded from a joblib file trained offline (see the
top-level ml/training/ scripts). Nothing here trains automatically at import or app
startup, per the MVP performance requirement.

Production: DefectDetector's predict() signature (features in, label+confidence out) is the
seam where a YOLO/TensorFlow CNN inference service would be substituted; callers (the
services/quality.py layer) do not need to change.
"""
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier

MODEL_FORMAT_VERSION = 1
DEFECT_MODEL_FILENAME = "defect_detector.joblib"
PROCESS_MODEL_FILENAME = "process_quality.joblib"

SEVERITY_BY_CLASS = {
    "NORMAL": "none", "WARPING": "medium", "STRINGING": "low",
    "LAYER_SHIFT": "high", "CLOGGING": "high",
}


class ModelNotTrainedError(RuntimeError):
    """No trained model artifact was found. Run the training script first."""


@dataclass
class DefectPrediction:
    predicted_class: str
    confidence: float
    severity: str
    class_probabilities: dict[str, float]


class DefectDetector:
    """Wraps a RandomForestClassifier trained on hand-engineered CV features (see
    quality_features.py). See module docstring for the production substitution point."""

    def __init__(self, classifier: RandomForestClassifier, feature_names: list[str],
                classes: list[str], trained_at: str, model_version: str):
        self.classifier = classifier
        self.feature_names = feature_names
        self.classes = classes
        self.trained_at = trained_at
        self.model_version = model_version

    def predict(self, features: np.ndarray) -> DefectPrediction:
        probabilities = self.classifier.predict_proba(features.reshape(1, -1))[0]
        order = np.argsort(probabilities)[::-1]
        top = self.classifier.classes_[order[0]]
        classes_and_probs = zip(self.classifier.classes_, probabilities, strict=True)
        prob_map = {cls: round(float(p), 4) for cls, p in classes_and_probs}
        return DefectPrediction(
            predicted_class=str(top), confidence=round(float(probabilities[order[0]]), 4),
            severity=SEVERITY_BY_CLASS.get(str(top), "unknown"), class_probabilities=prob_map,
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "format_version": MODEL_FORMAT_VERSION, "classifier": self.classifier,
            "feature_names": self.feature_names, "classes": self.classes,
            "trained_at": self.trained_at, "model_version": self.model_version,
        }, path)

    @classmethod
    def load(cls, path: Path) -> "DefectDetector":
        if not path.exists():
            raise ModelNotTrainedError(
                f"No trained defect-detection model at {path}. Run "
                "ml/training/train_defect_model.py first."
            )
        payload = joblib.load(path)
        if payload.get("format_version") != MODEL_FORMAT_VERSION:
            raise ModelNotTrainedError(
                f"Model at {path} was saved with an incompatible format; retrain it."
            )
        return cls(payload["classifier"], payload["feature_names"], payload["classes"],
                  payload["trained_at"], payload["model_version"])


@dataclass
class ProcessPrediction:
    predicted_quality: str
    quality_probabilities: dict[str, float]
    anomaly_score: float
    is_anomaly: bool
    risk_level: str


class ProcessQualityModel:
    """RandomForestClassifier (predicted_quality) + IsolationForest (anomaly_score) over
    print-process parameters: nozzle temp, bed temp, speed, layer height, extrusion rate,
    duration."""

    def __init__(self, quality_clf: RandomForestClassifier, anomaly_clf: IsolationForest,
                feature_names: list[str], trained_at: str, model_version: str):
        self.quality_clf = quality_clf
        self.anomaly_clf = anomaly_clf
        self.feature_names = feature_names
        self.trained_at = trained_at
        self.model_version = model_version

    def predict(self, features: np.ndarray) -> ProcessPrediction:
        x = features.reshape(1, -1)
        probabilities = self.quality_clf.predict_proba(x)[0]
        top_index = int(np.argmax(probabilities))
        top = self.quality_clf.classes_[top_index]
        classes_and_probs = zip(self.quality_clf.classes_, probabilities, strict=True)
        prob_map = {cls: round(float(p), 4) for cls, p in classes_and_probs}
        raw_score = float(self.anomaly_clf.decision_function(x)[0])  # higher = more normal
        is_anomaly = bool(self.anomaly_clf.predict(x)[0] == -1)
        anomaly_score = round(max(0.0, min(1.0, 0.5 - raw_score)), 4)  # 0=normal .. 1=anomalous
        if is_anomaly or anomaly_score > 0.7 or top == "poor":
            risk = "HIGH"
        elif anomaly_score > 0.4 or top == "fair":
            risk = "MEDIUM"
        else:
            risk = "LOW"
        return ProcessPrediction(str(top), prob_map, anomaly_score, is_anomaly, risk)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "format_version": MODEL_FORMAT_VERSION, "quality_clf": self.quality_clf,
            "anomaly_clf": self.anomaly_clf, "feature_names": self.feature_names,
            "trained_at": self.trained_at, "model_version": self.model_version,
        }, path)

    @classmethod
    def load(cls, path: Path) -> "ProcessQualityModel":
        if not path.exists():
            raise ModelNotTrainedError(
                f"No trained process-quality model at {path}. Run "
                "ml/training/train_process_model.py first."
            )
        payload = joblib.load(path)
        if payload.get("format_version") != MODEL_FORMAT_VERSION:
            raise ModelNotTrainedError(
                f"Model at {path} was saved with an incompatible format; retrain it."
            )
        return cls(payload["quality_clf"], payload["anomaly_clf"], payload["feature_names"],
                  payload["trained_at"], payload["model_version"])
