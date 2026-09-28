"""Synthetic print-process parameter dataset (predictive quality analytics, Module A3).

Safe operating ranges are documented constants (not hidden magic numbers) so the training
script, the API validation, and the manufacturing anomaly detector (Phase 7) can share them.
No real production telemetry was supplied with this project; this generator produces a
plausible parameter distribution with a continuous risk score, then labels quality from it.
As required: "This metric was obtained using the supplied demonstration dataset and does not
represent industrial validation."
"""
import random

import numpy as np

FEATURE_NAMES = ["nozzle_temp_c", "bed_temp_c", "speed_mm_s", "layer_height_mm",
                 "extrusion_rate_pct", "duration_min"]

# (low, high) of the safe operating band for each parameter; used for scoring AND for the
# API's live "suspicious" checks in the manufacturing module (Phase 7).
SAFE_RANGES = {
    "nozzle_temp_c": (190.0, 220.0), "bed_temp_c": (50.0, 70.0), "speed_mm_s": (30.0, 80.0),
    "layer_height_mm": (0.12, 0.28), "extrusion_rate_pct": (92.0, 108.0),
    "duration_min": (10.0, 300.0),
}
QUALITY_CLASSES = ["good", "fair", "poor"]


def _deviation_score(values: dict[str, float]) -> float:
    """0.0 (dead centre of every safe range) upward; unbounded above. duration_min excluded
    (it doesn't affect print quality, only job length)."""
    total = 0.0
    for name, (low, high) in SAFE_RANGES.items():
        if name == "duration_min":
            continue
        centre, half = (low + high) / 2, (high - low) / 2
        total += abs(values[name] - centre) / half
    return total


def _label_from_score(score: float, rng: random.Random) -> str:
    noisy = max(0.0, score + rng.gauss(0, 0.15))  # label noise: real quality isn't deterministic
    if noisy < 0.9:
        return "good"
    if noisy < 2.2:
        return "fair"
    return "poor"


def _sample_row(rng: random.Random, regime: str) -> dict[str, float]:
    """regime: 'normal' stays inside/near the safe band; 'extreme' samples well outside it
    (used to give the anomaly detector clear outliers to learn from, and to build the
    TAMPERING demo scenario)."""
    values = {}
    for name, (low, high) in SAFE_RANGES.items():
        centre, half = (low + high) / 2, (high - low) / 2
        if regime == "normal":
            # 0.22 tuned empirically for balanced good/fair/poor labels
            values[name] = rng.gauss(centre, half * 0.22)
        else:
            direction = rng.choice([-1, 1])
            values[name] = centre + direction * half * rng.uniform(1.8, 4.0)
        values[name] = max(0.0, values[name])
    return values


def generate_process_dataset(n_normal: int, n_extreme: int, seed: int = 0):
    """Yield (feature_dict, quality_label, is_extreme_regime) rows, deterministic given seed."""
    # Deterministic synthetic-data generation, not a security context; secrets does not
    # support seeding, which reproducibility here requires.
    rng = random.Random(seed)  # noqa: S311  # nosec B311
    rows = [("normal", False)] * n_normal + [("extreme", True)] * n_extreme
    rng.shuffle(rows)
    for regime, is_extreme in rows:
        values = _sample_row(rng, regime)
        label = _label_from_score(_deviation_score(values), rng)
        yield values, label, is_extreme


def to_feature_vector(values: dict[str, float]) -> np.ndarray:
    return np.asarray([values[name] for name in FEATURE_NAMES], dtype=np.float64)
