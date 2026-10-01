"""Hybrid manufacturing anomaly detection (Module G).

Two layers, checked in order:
1. Hard safety thresholds (the same SAFE_RANGES used by predictive quality analytics and the
   G-code analyzer, so "safe" means one consistent thing across the whole platform). A clear
   threshold breach is reported immediately with an exact, human-readable reason and HIGH risk.
2. If every hard threshold passes, the trained Isolation Forest from Module A3
   (app/ml/registry.get_process_model) checks the FULL parameter combination for a subtler,
   statistical anomaly that no single threshold would catch. This layer is optional: if no
   model has been trained yet, only the threshold layer runs (still fully functional).
"""
from dataclasses import dataclass

import numpy as np

from app.ml.process_dataset import SAFE_RANGES
from app.ml.quality_model import ModelNotTrainedError

# telemetry field name -> SAFE_RANGES key (and a human label for the reason string)
_THRESHOLD_FIELDS = [
    ("temperature", "nozzle_temp_c", "Nozzle temperature"),
    ("bed_temperature", "bed_temp_c", "Bed temperature"),
    ("speed", "speed_mm_s", "Print speed"),
    ("flow_rate", "extrusion_rate_pct", "Extrusion/flow rate"),
]
_EXCESS_FACTOR = 1.15  # matches the G-code analyzer's HIGH-vs-MEDIUM excess threshold


@dataclass
class AnomalyResult:
    anomaly: bool
    risk: str  # NONE | MEDIUM | HIGH
    method: str  # threshold | isolation_forest | none
    reasons: list[str]


def _threshold_check(telemetry: dict) -> list[str]:
    reasons = []
    for field, range_key, label in _THRESHOLD_FIELDS:
        value = telemetry.get(field)
        if value is None:
            continue
        low, high = SAFE_RANGES[range_key]
        if value > high * _EXCESS_FACTOR or value < low / _EXCESS_FACTOR:
            reasons.append(f"{label} {value:.1f} is far outside the safe range "
                           f"({low:.0f}-{high:.0f})")
        elif not (low <= value <= high):
            reasons.append(f"{label} {value:.1f} exceeded the configured safety threshold "
                           f"(safe range {low:.0f}-{high:.0f})")
    return reasons


def detect_anomaly(telemetry: dict, process_model=None) -> AnomalyResult:
    threshold_reasons = _threshold_check(telemetry)
    if threshold_reasons:
        return AnomalyResult(True, "HIGH", "threshold", threshold_reasons)

    if process_model is not None:
        vector = np.asarray([
            telemetry.get("temperature", 0.0), telemetry.get("bed_temperature", 0.0),
            telemetry.get("speed", 0.0), 0.2,  # layer_height_mm: not live telemetry, use a safe default
            telemetry.get("flow_rate", 100.0), 0.0,  # duration_min: not meaningful per-tick
        ], dtype=np.float64)
        try:
            prediction = process_model.predict(vector)
        except ModelNotTrainedError:
            return AnomalyResult(False, "NONE", "none", [])
        if prediction.is_anomaly:
            return AnomalyResult(True, "MEDIUM", "isolation_forest", [
                f"Isolation Forest flagged this parameter combination as statistically unusual "
                f"(anomaly score {prediction.anomaly_score}), though no single value exceeded "
                f"its safety threshold"])
    return AnomalyResult(False, "NONE", "none", [])
