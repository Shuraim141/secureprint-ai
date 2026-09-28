"""Fixed-length feature vector for the defect classifier (classical CV, not a learned embedding).

Deliberately hand-engineered and documented, per the MVP's "lightweight fallback" design:
Production: replace DefectDetector's feature+RandomForest pipeline with a YOLO/TensorFlow
inference service (see ml/quality_model.py) when GPU infrastructure is available.
"""
import cv2
import numpy as np

from app.cv.inspection import preprocess

FEATURE_NAMES = [
    "brightness_mean", "brightness_std", "edge_density", "sharpness_variance",
    "contour_count_norm", "sig_contour_count_norm", "sig_contour_area_mean_norm",
    "sig_contour_area_std_norm", "row_line_regularity", "horizontal_discontinuity",
    "diagonal_line_energy", "hole_count_norm",
]


def _row_line_regularity(image: np.ndarray) -> float:
    """High for regular horizontal layer lines (NORMAL), lower when disrupted."""
    row_means = image.mean(axis=1)
    diffs = np.diff(row_means)
    if diffs.std() < 1e-6:
        return 0.0
    # autocorrelation peak at small lags indicates periodic layer banding
    diffs = diffs - diffs.mean()
    autocorr = np.correlate(diffs, diffs, mode="full")[len(diffs) - 1:]
    autocorr = autocorr / (autocorr[0] + 1e-9)
    return float(np.max(autocorr[2:8])) if len(autocorr) > 8 else 0.0


def _horizontal_discontinuity(image: np.ndarray) -> float:
    """Large for a single sharp jump in row-mean brightness (LAYER_SHIFT signature)."""
    row_means = image.mean(axis=1).astype(np.float64)
    jumps = np.abs(np.diff(row_means))
    return float(jumps.max()) if len(jumps) else 0.0


def _diagonal_line_energy(edges: np.ndarray) -> float:
    """High when many short, randomly-angled edge segments exist (STRINGING signature),
    via the density of Hough line detections at non-cardinal angles."""
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=12, minLineLength=6, maxLineGap=2)
    if lines is None:
        return 0.0
    angles = np.degrees(np.arctan2(lines[:, 0, 3] - lines[:, 0, 1], lines[:, 0, 2] - lines[:, 0, 0]))
    diagonal = np.abs(np.abs(np.mod(angles, 90)) - 45) < 35  # not near 0/90 degrees
    return float(diagonal.sum()) / edges.size * 1000


def _hole_count(image: np.ndarray) -> int:
    """Count small dark blobs inside the bright print body (CLOGGING signature)."""
    _, dark = cv2.threshold(image, 90, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return sum(1 for c in contours if 8 < cv2.contourArea(c) < (image.size * 0.05))


def extract_features(gray: np.ndarray, target_size: int) -> np.ndarray:
    """gray: full-resolution grayscale array. Returns a float32 vector of FEATURE_NAMES length."""
    image = preprocess(gray, target_size)
    edges = cv2.Canny(image, 60, 160)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    areas = np.array([cv2.contourArea(c) for c in contours], dtype=np.float64)
    significant = areas[areas > 4.0]
    norm = float(target_size * target_size)

    features = [
        float(image.mean()) / 255.0,
        float(image.std()) / 255.0,
        float(np.count_nonzero(edges)) / edges.size,
        min(float(cv2.Laplacian(image, cv2.CV_64F).var()) / 500.0, 5.0),
        min(len(contours) / (norm / 200.0), 5.0),
        min(len(significant) / (norm / 200.0), 5.0),
        min((float(significant.mean()) if len(significant) else 0.0) / norm, 1.0),
        min((float(significant.std()) if len(significant) else 0.0) / norm, 1.0),
        _row_line_regularity(image),
        min(_horizontal_discontinuity(image) / 40.0, 3.0),
        min(_diagonal_line_energy(edges), 5.0),
        min(_hole_count(image) / 10.0, 3.0),
    ]
    return np.asarray(features, dtype=np.float32)
