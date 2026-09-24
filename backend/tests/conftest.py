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
    "HARDWARE_PROFILE": "low",
})

import pytest  # noqa: E402

PASSWORD = "Str0ng-Passw0rd!"


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
