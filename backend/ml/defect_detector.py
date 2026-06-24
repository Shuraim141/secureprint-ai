#!/usr/bin/env python3
"""
============================================================
STEP 2: AI QUALITY CONTROL ENGINE — DEFECT DETECTION
File: backend/ml/defect_detector.py

This module implements:
  - CNN-based defect classification (TensorFlow/Keras)
  - YOLO-based real-time defect localization (Ultralytics)
  - OpenCV preprocessing pipeline
  - Predictive quality scoring

Run: python backend/ml/defect_detector.py
============================================================
"""

import os
import numpy as np
import cv2
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, callbacks
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import json
import logging
from pathlib import Path
import datetime

# ── Configuration ───────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("DefectDetector")

IMG_SIZE       = (224, 224)
BATCH_SIZE     = 32
EPOCHS         = 50
NUM_CLASSES    = 5          # Normal, Warping, Stringing, LayerShift, Clogging
LEARNING_RATE  = 1e-4
MODEL_PATH     = "/opt/secureprint/models/defect_detection/model.h5"
DATA_PATH      = "/opt/secureprint/data/training"

DEFECT_CLASSES = [
    "NORMAL",
    "WARPING",        # Layer separation from bed
    "STRINGING",      # Thin filament trails between parts
    "LAYER_SHIFT",    # Misaligned layers (X/Y axis slip)
    "CLOGGING",       # Nozzle blockage artifacts
]


# ── 2.1 OpenCV Preprocessing Pipeline ───────────────────────
class PrintImagePreprocessor:
    """
    Computer vision preprocessing for 3D print inspection images.
    Applies: denoising → CLAHE enhancement → edge detection → normalization
    """

    def __init__(self, target_size=IMG_SIZE):
        self.target_size = target_size
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    def preprocess(self, image_path: str) -> np.ndarray:
        """Load and preprocess a single print image."""
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Cannot read image: {image_path}")

        # Convert BGR → RGB
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Resize to standard input
        img = cv2.resize(img, self.target_size)

        # Denoise (bilateral filter preserves edges)
        img = cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)

        # CLAHE enhancement on L channel (LAB space)
        lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
        lab[:, :, 0] = self.clahe.apply(lab[:, :, 0])
        img = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)

        # Normalize to [0, 1]
        img = img.astype(np.float32) / 255.0

        return img

    def compute_layer_quality_metrics(self, image_path: str) -> dict:
        """
        Extract quantitative metrics from print layer image.
        Returns thickness uniformity, surface roughness estimate, void ratio.
        """
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return {}

        img_resized = cv2.resize(img, self.target_size)

        # Edge density → surface roughness indicator
        edges = cv2.Canny(img_resized, 50, 150)
        edge_density = np.sum(edges > 0) / edges.size

        # Local variance → uniformity (low variance = more uniform)
        local_var = cv2.Laplacian(img_resized, cv2.CV_64F).var()

        # Dark pixel ratio → potential void/gap indicator
        _, thresh = cv2.threshold(img_resized, 50, 255, cv2.THRESH_BINARY_INV)
        void_ratio = np.sum(thresh > 0) / thresh.size

        # Texture analysis using Haralick-like features
        contrast = np.std(img_resized.astype(float))

        return {
            "edge_density":      round(float(edge_density), 4),
            "surface_roughness": round(float(local_var), 4),
            "void_ratio":        round(float(void_ratio), 4),
            "contrast":          round(float(contrast), 4),
            "quality_score":     round(self._compute_quality_score(
                                      edge_density, local_var, void_ratio), 3)
        }

    def _compute_quality_score(self, edge_density, local_var, void_ratio) -> float:
        """
        Weighted quality score: 0 (worst) → 1 (perfect).
        Lower edge density, lower variance, and lower void ratio → better quality.
        """
        edge_score = max(0, 1 - edge_density * 10)
        var_score  = max(0, 1 - local_var / 5000)
        void_score = max(0, 1 - void_ratio * 5)
        return 0.4 * edge_score + 0.3 * var_score + 0.3 * void_score


# ── 2.2 CNN Defect Classifier ────────────────────────────────
class DefectClassificationModel:
    """
    Transfer-learning CNN based on MobileNetV2 for defect classification.
    Fine-tuned on 3D printing defect dataset.
    """

    def __init__(self, num_classes=NUM_CLASSES):
        self.num_classes = num_classes
        self.model = None
        self.history = None

    def build(self) -> keras.Model:
        """
        Custom CNN Architecture (offline — no internet required):
          Input(224x224x3)
          -> Conv2D(32) -> BN -> MaxPool
          -> Conv2D(64) -> BN -> MaxPool
          -> Conv2D(128) -> BN -> MaxPool
          -> Conv2D(256) -> BN -> GlobalAvgPool
          -> Dense(256) -> Dropout(0.5)
          -> Dense(128) -> Dropout(0.3)
          -> Softmax(5 classes)
        NOTE: In production swap this for MobileNetV2(weights=imagenet)
        for higher accuracy via transfer learning.
        """
        log.info("Building custom CNN (offline mode — no pretrained weights needed)...")

        inputs = keras.Input(shape=(*IMG_SIZE, 3), name="print_image")

        # Block 1: low-level features (edges, textures)
        x = layers.Conv2D(32, (3, 3), padding="same", activation="relu")(inputs)
        x = layers.BatchNormalization()(x)
        x = layers.MaxPooling2D((2, 2))(x)

        # Block 2: mid-level features (layer line patterns)
        x = layers.Conv2D(64, (3, 3), padding="same", activation="relu")(x)
        x = layers.BatchNormalization()(x)
        x = layers.MaxPooling2D((2, 2))(x)

        # Block 3: higher-level features (defect shapes)
        x = layers.Conv2D(128, (3, 3), padding="same", activation="relu")(x)
        x = layers.BatchNormalization()(x)
        x = layers.MaxPooling2D((2, 2))(x)

        # Block 4: complex defect patterns
        x = layers.Conv2D(256, (3, 3), padding="same", activation="relu")(x)
        x = layers.BatchNormalization()(x)
        x = layers.GlobalAveragePooling2D()(x)

        # Classifier head
        x = layers.Dense(256, activation="relu")(x)
        x = layers.Dropout(0.5)(x)
        x = layers.Dense(128, activation="relu")(x)
        x = layers.Dropout(0.3)(x)
        outputs = layers.Dense(self.num_classes, activation="softmax", name="defect_class")(x)

        self.model = keras.Model(inputs, outputs, name="SecurePrint_DefectCNN")
        self.model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=LEARNING_RATE),
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"]
        )

        log.info(f"Custom CNN built: {self.model.count_params():,} parameters")
        return self.model

    def unfreeze_and_finetune(self, layers_to_unfreeze=50):
        """Phase 2: reduce LR for fine-tuning (all layers already trainable in custom CNN)."""
        self.model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=LEARNING_RATE / 10),
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"]
        )
        log.info("Fine-tuning: reduced learning rate applied")

    def train(self, X_train, y_train, X_val, y_val) -> dict:
        """Two-phase training: feature extraction then fine-tuning."""
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

        cbs = [
            callbacks.EarlyStopping(patience=10, restore_best_weights=True),
            callbacks.ModelCheckpoint(MODEL_PATH, save_best_only=True),
            callbacks.ReduceLROnPlateau(factor=0.5, patience=5, min_lr=1e-7),
            callbacks.TensorBoard(log_dir="/opt/secureprint/logs/tensorboard")
        ]

        # Phase 1: Feature extraction (frozen base)
        log.info("Phase 1: Feature extraction training...")
        self.history = self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=EPOCHS // 2,
            batch_size=BATCH_SIZE,
            callbacks=cbs
        )

        # Phase 2: Fine-tuning (partial unfreeze)
        log.info("Phase 2: Fine-tuning...")
        self.unfreeze_and_finetune()
        self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=EPOCHS // 2,
            batch_size=BATCH_SIZE // 2,
            callbacks=cbs
        )

        return self.history.history

    def predict(self, image_array: np.ndarray) -> dict:
        """
        Predict defect class and confidence for a preprocessed image.
        Returns class name, confidence, and all class probabilities.
        """
        if self.model is None:
            self.load()

        img_batch = np.expand_dims(image_array, axis=0)
        probs = self.model.predict(img_batch, verbose=0)[0]
        pred_idx = np.argmax(probs)

        return {
            "defect_class":     DEFECT_CLASSES[pred_idx],
            "confidence":       round(float(probs[pred_idx]), 4),
            "is_defective":     DEFECT_CLASSES[pred_idx] != "NORMAL",
            "probabilities":    {
                cls: round(float(p), 4)
                for cls, p in zip(DEFECT_CLASSES, probs)
            },
            "timestamp":        datetime.datetime.utcnow().isoformat()
        }

    def load(self):
        """Load saved model from disk."""
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Model not found at {MODEL_PATH}. Train first.")
        self.model = keras.models.load_model(MODEL_PATH)
        log.info("Model loaded from disk")

    def evaluate(self, X_test, y_test):
        """Full evaluation with classification report."""
        y_pred = np.argmax(self.model.predict(X_test), axis=1)
        report = classification_report(
            y_test, y_pred,
            target_names=DEFECT_CLASSES,
            output_dict=True
        )
        log.info("\n" + classification_report(y_test, y_pred, target_names=DEFECT_CLASSES))
        return report


# ── 2.3 YOLO Real-Time Defect Localization ───────────────────
class YOLODefectLocalizer:
    """
    YOLOv8 model for real-time bounding-box defect localization.
    Identifies WHERE defects occur on the print bed.
    """

    def __init__(self, model_path: str = "yolov8n.pt"):
        try:
            from ultralytics import YOLO
            self.model = YOLO(model_path)
            log.info("YOLO model loaded")
        except Exception as e:
            log.warning(f"YOLO unavailable: {e}. Install ultralytics.")
            self.model = None

    def detect(self, image_path: str, confidence_threshold: float = 0.5) -> list:
        """
        Run YOLO inference on a print frame.
        Returns list of detected defect regions with bounding boxes.
        """
        if self.model is None:
            return []

        results = self.model(image_path, conf=confidence_threshold)
        detections = []

        for r in results:
            for box in r.boxes:
                detections.append({
                    "class_id":   int(box.cls),
                    "class_name": DEFECT_CLASSES[int(box.cls)] if int(box.cls) < len(DEFECT_CLASSES) else "UNKNOWN",
                    "confidence": round(float(box.conf), 4),
                    "bbox":       [round(float(x), 2) for x in box.xyxy[0].tolist()],
                    "area_ratio": round(float(
                        (box.xyxy[0][2] - box.xyxy[0][0]) *
                        (box.xyxy[0][3] - box.xyxy[0][1]) /
                        (r.orig_shape[0] * r.orig_shape[1])
                    ), 4)
                })

        return detections

    def annotate_image(self, image_path: str, output_path: str):
        """Save annotated image with defect bounding boxes drawn."""
        if self.model is None:
            return
        results = self.model(image_path)
        results[0].save(filename=output_path)


# ── 2.4 Predictive Quality Analytics ────────────────────────
class PredictiveQualityEngine:
    """
    Time-series analysis of print parameters to PREDICT quality degradation
    BEFORE defects become visible.
    Uses: temperature trends, extrusion rate variance, vibration signatures.
    """

    def __init__(self):
        from sklearn.ensemble import IsolationForest, RandomForestClassifier
        self.anomaly_model    = IsolationForest(contamination=0.1, random_state=42)
        self.prediction_model = RandomForestClassifier(n_estimators=200, random_state=42)

    def extract_process_features(self, telemetry: dict) -> np.ndarray:
        """
        Convert raw printer telemetry into ML feature vector.
        
        Telemetry keys expected:
          - nozzle_temp, bed_temp, chamber_temp
          - extrusion_rate, fan_speed, print_speed
          - x_pos, y_pos, z_pos
          - current_layer, total_layers
          - elapsed_time_s
        """
        features = [
            telemetry.get("nozzle_temp", 200),
            telemetry.get("bed_temp", 60),
            telemetry.get("chamber_temp", 30),
            telemetry.get("extrusion_rate", 100),
            telemetry.get("fan_speed", 100),
            telemetry.get("print_speed", 50),
            telemetry.get("layer_height", 0.2),
            telemetry.get("current_layer", 1),
            # Derived features
            telemetry.get("nozzle_temp", 200) - telemetry.get("bed_temp", 60),
            telemetry.get("extrusion_rate", 100) / max(telemetry.get("print_speed", 50), 1),
        ]
        return np.array(features).reshape(1, -1)

    def predict_failure_risk(self, telemetry_history: list) -> dict:
        """
        Given recent telemetry history, predict failure probability.
        Returns: risk_score (0-1), risk_level, recommended_actions.
        """
        if len(telemetry_history) < 5:
            return {"risk_score": 0.0, "risk_level": "UNKNOWN", "actions": []}

        features = np.array([
            self.extract_process_features(t).flatten()
            for t in telemetry_history
        ])

        # Statistical features across time window
        feature_mean = np.mean(features, axis=0)
        feature_std  = np.std(features, axis=0)
        feature_vec  = np.concatenate([feature_mean, feature_std]).reshape(1, -1)

        # Anomaly score from IsolationForest
        anomaly_score = self.anomaly_model.decision_function(
            feature_vec.reshape(1, -1)
        )[0]
        risk_score = max(0, min(1, 0.5 - anomaly_score))

        if risk_score < 0.3:
            risk_level = "LOW"
            actions = ["Continue nominal operation"]
        elif risk_score < 0.6:
            risk_level = "MEDIUM"
            actions = ["Inspect nozzle", "Check bed adhesion", "Review temperature stability"]
        elif risk_score < 0.8:
            risk_level = "HIGH"
            actions = ["Pause print", "Manual inspection required", "Check for warping"]
        else:
            risk_level = "CRITICAL"
            actions = ["STOP PRINT", "Emergency inspection", "Check for sabotage or tampering"]

        return {
            "risk_score":  round(float(risk_score), 3),
            "risk_level":  risk_level,
            "actions":     actions,
            "timestamp":   datetime.datetime.utcnow().isoformat()
        }


# ── 2.5 Synthetic Training Data Generator (for demo/testing) ─
def generate_synthetic_training_data(n_samples: int = 1000):
    """
    Generate synthetic training data for demonstration purposes.
    In production, use real labelled print images.
    Returns X (images) and y (labels).
    """
    log.info(f"Generating {n_samples} synthetic training samples...")
    X, y = [], []

    for i in range(n_samples):
        # Synthetic 224x224 RGB image (noise patterns simulating print layers)
        img = np.random.randint(50, 200, (*IMG_SIZE, 3), dtype=np.uint8)
        label = i % NUM_CLASSES

        # Add class-specific visual patterns
        if label == 1:  # Warping: add diagonal gradient
            grad = np.linspace(0, 100, IMG_SIZE[0]).astype(np.uint8)
            img[:, :, 0] = np.clip(img[:, :, 0] + grad[:, None], 0, 255)
        elif label == 2:  # Stringing: add thin horizontal lines
            for row in range(0, IMG_SIZE[0], 20):
                img[row, :, :] = 255
        elif label == 3:  # Layer shift: add offset block
            img[100:150, 80:130, 1] = 255
        elif label == 4:  # Clogging: add dark circular region
            center = (IMG_SIZE[0]//2, IMG_SIZE[1]//2)
            cv2.circle(img, center, 30, (10, 10, 10), -1)

        X.append(img.astype(np.float32) / 255.0)
        y.append(label)

    return np.array(X), np.array(y)


# ── Main: Training Pipeline ──────────────────────────────────
if __name__ == "__main__":
    log.info("=" * 60)
    log.info("  SecurePrint AI — Defect Detection Training Pipeline")
    log.info("=" * 60)

    # Generate or load training data
    log.info("Preparing training data...")
    X, y = generate_synthetic_training_data(n_samples=2000)

    X_train, X_temp, y_train, y_temp = train_test_split(X, y, test_size=0.3, random_state=42)
    X_val, X_test, y_val, y_test     = train_test_split(X_temp, y_temp, test_size=0.5, random_state=42)

    log.info(f"Train: {len(X_train)} | Val: {len(X_val)} | Test: {len(X_test)}")

    # Build and train model
    classifier = DefectClassificationModel()
    classifier.build()
    history = classifier.train(X_train, y_train, X_val, y_val)

    # Evaluate
    log.info("Evaluating on test set...")
    report = classifier.evaluate(X_test, y_test)

    # Save metrics
    metrics_path = "/opt/secureprint/models/defect_detection/metrics.json"
    os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
    with open(metrics_path, "w") as f:
        json.dump(report, f, indent=2)

    log.info(f"✅ Model saved to {MODEL_PATH}")
    log.info(f"✅ Metrics saved to {metrics_path}")
    log.info("")
    log.info("Next: Run python backend/ml/anomaly_detector.py")
