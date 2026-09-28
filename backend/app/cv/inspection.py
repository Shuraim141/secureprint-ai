"""OpenCV-based image preprocessing and inspection (classical CV, not a learned model).

Every function here operates on real pixel data passed in; nothing is hardcoded. Used both
as a visual inspection step (edges/contours/quality checks) and to feed features.py.
"""
import base64
import io

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

MAX_PIXELS = 20_000_000  # decompression-bomb guard (about a 4472x4472 image)


class ImageValidationError(ValueError):
    pass


def decode_image(data: bytes) -> np.ndarray:
    """Decode PNG/JPEG bytes to a grayscale uint8 array, with safety limits."""
    if not data:
        raise ImageValidationError("Image file is empty")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:  # verify() consumes the file; reopen
            if image.width * image.height > MAX_PIXELS:
                raise ImageValidationError("Image exceeds the maximum allowed pixel count")
            gray = image.convert("L")
            array = np.array(gray, dtype=np.uint8)
    except UnidentifiedImageError as exc:
        raise ImageValidationError("File is not a valid image") from exc
    except (OSError, ValueError) as exc:
        raise ImageValidationError(f"Corrupted or unreadable image: {exc}") from exc
    if array.size == 0 or min(array.shape) < 16:
        raise ImageValidationError("Image is too small to inspect (minimum 16x16)")
    return array


def preprocess(gray: np.ndarray, target_size: int) -> np.ndarray:
    """Resize to a square target size and mildly denoise. Used before feature extraction."""
    resized = cv2.resize(gray, (target_size, target_size), interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(resized, (3, 3), 0)


def to_png_base64(gray: np.ndarray) -> str:
    ok, buffer = cv2.imencode(".png", gray)
    if not ok:
        raise RuntimeError("Failed to encode image")  # pragma: no cover
    return base64.b64encode(buffer.tobytes()).decode("ascii")


def inspect(gray: np.ndarray, target_size: int) -> dict:
    """Run the classical CV pipeline and return a JSON-safe report plus base64 preview images.

    Steps: resize -> blur -> Canny edge detection -> external contour extraction ->
    per-contour area/perimeter stats -> basic sharpness/brightness quality checks.
    """
    processed = preprocess(gray, target_size)
    edges = cv2.Canny(processed, 60, 160)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    areas = np.array([cv2.contourArea(c) for c in contours], dtype=np.float64)
    significant = areas[areas > 4.0]

    overlay = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
    cv2.drawContours(overlay, [c for c, a in zip(contours, areas, strict=True) if a > 4.0],
                     -1, (0, 0, 255), 1)

    laplacian_var = float(cv2.Laplacian(processed, cv2.CV_64F).var())  # sharpness proxy
    edge_density = float(np.count_nonzero(edges)) / edges.size

    return {
        "target_size": target_size,
        "edge_density": round(edge_density, 6),
        "sharpness_variance": round(laplacian_var, 3),
        "brightness_mean": round(float(processed.mean()), 3),
        "brightness_std": round(float(processed.std()), 3),
        "contour_count": int(len(contours)),
        "significant_contour_count": int(len(significant)),
        "significant_contour_area_mean": round(float(significant.mean()), 3) if len(significant) else 0.0,
        "significant_contour_area_std": round(float(significant.std()), 3) if len(significant) else 0.0,
        "quality_flags": _quality_flags(laplacian_var, processed),
        "original_png_base64": to_png_base64(processed),
        "edges_png_base64": to_png_base64(edges),
        "contours_png_base64": to_png_base64(cv2.cvtColor(overlay, cv2.COLOR_BGR2GRAY)),
    }


def _quality_flags(sharpness: float, image: np.ndarray) -> list[str]:
    flags = []
    if sharpness < 15.0:
        flags.append("Image appears blurry (low sharpness variance)")
    if image.mean() < 25.0:
        flags.append("Image is very dark (possible underexposure)")
    if image.mean() > 230.0:
        flags.append("Image is very bright (possible overexposure/washout)")
    if image.std() < 8.0:
        flags.append("Very low contrast: little texture detected")
    return flags
