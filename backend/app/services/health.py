"""Health checks used by GET /health and scripts/health_check.py."""
import tempfile

from sqlalchemy import text

from app.config import get_settings
from app.database import engine


def _check_database() -> str:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:  # health endpoint must never raise
        return "error"


def _check_storage() -> str:
    try:
        directory = get_settings().storage_dir
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory):  # write test, auto-deleted
            pass
        return "ok"
    except OSError:
        return "error"


def _check_ml() -> str:
    # Phase 5 replaces this with a real model-load check. Reported honestly until then.
    return "not_configured"


def check_health() -> dict:
    database, storage, ml = _check_database(), _check_storage(), _check_ml()
    if database == "error" or storage == "error":
        status = "unhealthy"
    elif ml == "error":
        status = "degraded"
    else:
        status = "healthy"
    return {"status": status, "api": "ok", "database": database, "storage": storage, "ml": ml}
