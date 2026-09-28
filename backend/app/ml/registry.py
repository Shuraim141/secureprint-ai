"""Lazy, cached loading of trained ML models from disk (used by services/quality.py and the
health check). Models are never trained here and never auto-trained at import time."""
from functools import lru_cache

from app.config import get_settings
from app.ml.quality_model import (
    DEFECT_MODEL_FILENAME,
    PROCESS_MODEL_FILENAME,
    DefectDetector,
    ModelNotTrainedError,
    ProcessQualityModel,
)


@lru_cache
def get_defect_detector() -> DefectDetector:
    return DefectDetector.load(get_settings().model_dir / DEFECT_MODEL_FILENAME)


@lru_cache
def get_process_model() -> ProcessQualityModel:
    return ProcessQualityModel.load(get_settings().model_dir / PROCESS_MODEL_FILENAME)


def clear_model_cache() -> None:
    """Called by tests after training a fresh model, so the next request reloads it."""
    get_defect_detector.cache_clear()
    get_process_model.cache_clear()


def ml_health() -> str:
    """'ok' | 'not_configured' | 'error' — never raises, used by GET /health."""
    settings = get_settings()
    missing = [f for f in (DEFECT_MODEL_FILENAME, PROCESS_MODEL_FILENAME)
              if not (settings.model_dir / f).exists()]
    if missing:
        return "not_configured"
    try:
        get_defect_detector()
        get_process_model()
    except ModelNotTrainedError:
        return "error"
    except Exception:  # a corrupted joblib file must not crash the health check
        return "error"
    return "ok"
