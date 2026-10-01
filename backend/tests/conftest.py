"""Test fixtures. Environment is set BEFORE the app is imported so tests use a throwaway
SQLite database and never touch your real data."""
import base64
import os
import secrets
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="secureprint-test-"))
os.environ.update({
    "ENVIRONMENT": "test",
    "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}",
    "STORAGE_DIR": str(_TMP / "storage"),
    "JWT_SECRET": secrets.token_urlsafe(48),
    "MASTER_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
    "MAX_FAILED_LOGINS": "3",
    "LOCKOUT_MINUTES": "15",
    "ACCESS_TOKEN_MINUTES": "30",
    "CORS_ORIGINS": "http://localhost:5173",
    # "high": fast simulator ticks (0.5s) so manufacturing tests do not wait several
    # seconds per tick. The trained_models fixture hardcodes its own small sizes below,
    # so this does not make the ML training fixture slower.
    "HARDWARE_PROFILE": "high",
    "MAX_UPLOAD_MB": "1",
})

_MODEL_DIR = _TMP / "models"
os.environ["MODEL_DIR"] = str(_MODEL_DIR)

import pytest  # noqa: E402

PASSWORD = "Str0ng-Passw0rd!"


def _train_tiny_models() -> None:
    """Real training (not mocked), just small and fast, so /api/quality tests exercise the
    actual predict path end to end."""
    import numpy as np
    from sklearn.ensemble import IsolationForest, RandomForestClassifier

    from app.cv.inspection import decode_image
    from app.ml.process_dataset import FEATURE_NAMES as PROCESS_FEATURES
    from app.ml.process_dataset import generate_process_dataset, to_feature_vector
    from app.ml.quality_dataset import CLASSES, generate_dataset
    from app.ml.quality_features import FEATURE_NAMES as IMAGE_FEATURES
    from app.ml.quality_features import extract_features
    from app.ml.quality_model import (
        DEFECT_MODEL_FILENAME,
        PROCESS_MODEL_FILENAME,
        DefectDetector,
        ProcessQualityModel,
    )

    X, y = [], []
    for label, png in generate_dataset(samples_per_class=15, seed=1, size=64):
        X.append(extract_features(decode_image(png), 48))
        y.append(label)
    clf = RandomForestClassifier(n_estimators=30, random_state=1, n_jobs=-1)
    clf.fit(np.array(X), np.array(y))
    DefectDetector(clf, IMAGE_FEATURES, CLASSES, "test", "test-defect-v1").save(
        _MODEL_DIR / DEFECT_MODEL_FILENAME)

    pX, py = [], []
    for values, label, _ in generate_process_dataset(n_normal=120, n_extreme=40, seed=7):
        pX.append(to_feature_vector(values))
        py.append(label)
    pX = np.array(pX)
    qclf = RandomForestClassifier(n_estimators=30, random_state=7, n_jobs=-1)
    qclf.fit(pX, np.array(py))
    iso = IsolationForest(n_estimators=30, contamination=0.15, random_state=7, n_jobs=-1)
    iso.fit(pX)
    ProcessQualityModel(qclf, iso, PROCESS_FEATURES, "test", "test-process-v1").save(
        _MODEL_DIR / PROCESS_MODEL_FILENAME)


@pytest.fixture(scope="session")
def trained_models(client):
    """Trains tiny real models once per test session, then clears the app's model cache."""
    from app.ml.registry import clear_model_cache

    _train_tiny_models()
    clear_model_cache()
    yield



@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:  # runs lifespan: creates tables, seeds roles
        yield test_client


@pytest.fixture(scope="session")
def make_user(client):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import Role, User
    from app.security.passwords import hash_password

    def _make(username: str, role: str = "VIEWER", password: str = PASSWORD) -> None:
        with SessionLocal() as db:
            if db.execute(select(User).where(User.username == username)).scalar_one_or_none():
                return
            role_row = db.execute(select(Role).where(Role.name == role)).scalar_one()
            db.add(User(username=username, role_id=role_row.id,
                        password_hash=hash_password(password)))
            db.commit()

    return _make


@pytest.fixture(scope="session")
def headers_for(client, make_user):
    cache: dict[str, dict[str, str]] = {}

    def _headers(role: str) -> dict[str, str]:
        if role not in cache:
            username = f"t_{role.lower()}"
            make_user(username, role)
            response = client.post("/api/auth/login",
                                   json={"username": username, "password": PASSWORD})
            assert response.status_code == 200, response.text
            cache[role] = {"Authorization": f"Bearer {response.json()['access_token']}"}
        return cache[role]

    return _headers
