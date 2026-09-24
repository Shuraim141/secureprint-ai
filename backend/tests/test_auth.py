"""Authentication, lockout, token handling and user management (needs the web stack)."""
from datetime import datetime, timedelta, timezone

import jwt
from conftest import PASSWORD


def _login(client, username, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_login_success_returns_token_and_role(client, make_user):
    make_user("alice_eng", "ENGINEER")
    response = _login(client, "alice_eng")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["role"] == "ENGINEER"
    assert body["access_token"] and body["expires_in"] == 1800


def test_wrong_password_and_unknown_user_look_identical(client, make_user):
    make_user("bob_viewer", "VIEWER")
    wrong = _login(client, "bob_viewer", "definitely-wrong")
    unknown = _login(client, "no_such_user", "definitely-wrong")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_account_lockout_after_repeated_failures(client, make_user):
    make_user("carol_locked", "VIEWER")
    for _ in range(3):  # MAX_FAILED_LOGINS=3 in conftest
        assert _login(client, "carol_locked", "bad-password-x").status_code == 401
    blocked = _login(client, "carol_locked", PASSWORD)  # correct password, still blocked
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


def test_me_requires_valid_token(client, headers_for):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    ok = client.get("/api/auth/me", headers=headers_for("ENGINEER"))
    assert ok.status_code == 200 and ok.json()["role"] == "ENGINEER"


def test_expired_wrong_secret_and_alg_none_tokens_rejected(client, headers_for):
    user_id = client.get("/api/auth/me", headers=headers_for("VIEWER")).json()["id"]
    from app.config import get_settings

    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "jti": "forged", "type": "access", "iat": now,
               "exp": now + timedelta(minutes=5)}
    secret = get_settings().jwt_secret
    expired = jwt.encode({**payload, "exp": now - timedelta(minutes=1)}, secret, "HS256")
    wrong_key = jwt.encode(payload, "attacker-key-" + "q" * 40, "HS256")
    unsigned = jwt.encode(payload, "", algorithm="none")
    for token in (expired, wrong_key, unsigned):
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_logout_revokes_token(client, make_user):
    make_user("dave_logout", "VIEWER")
    token = _login(client, "dave_logout").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_passwords_are_stored_as_argon2id_hashes(client, make_user):
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import User

    make_user("erin_hash", "VIEWER")
    with SessionLocal() as db:
        stored = db.execute(select(User.password_hash).where(User.username == "erin_hash")).scalar_one()
    assert stored.startswith("$argon2id$") and PASSWORD not in stored


def test_admin_can_create_user_and_others_cannot(client, headers_for):
    payload = {"username": "new.user", "password": "An0ther-Str0ng-Pass", "role": "AUDITOR"}
    assert client.post("/api/auth/users", json=payload, headers=headers_for("ENGINEER")).status_code == 403
    created = client.post("/api/auth/users", json=payload, headers=headers_for("ADMIN"))
    assert created.status_code == 201 and created.json()["role"] == "AUDITOR"
    assert "password" not in created.text
    assert client.post("/api/auth/users", json=payload, headers=headers_for("ADMIN")).status_code == 409
    assert _login(client, "new.user", "An0ther-Str0ng-Pass").status_code == 200


def test_user_creation_validation(client, headers_for):
    admin = headers_for("ADMIN")
    weak = {"username": "weakling", "password": "short", "role": "VIEWER"}
    bad_role = {"username": "badrole", "password": "Str0ng-Passw0rd!", "role": "GOD_MODE"}
    contains_name = {"username": "mallory99", "password": "xxmallory99xx", "role": "VIEWER"}
    for body in (weak, bad_role, contains_name):
        assert client.post("/api/auth/users", json=body, headers=admin).status_code == 422


def test_validation_errors_do_not_echo_submitted_password(client):
    secret_value = "P" * 300  # exceeds max_length=256 -> 422
    response = client.post("/api/auth/login", json={"username": "x", "password": secret_value})
    assert response.status_code == 422
    assert "PPPPPPPPPP" not in response.text


def test_role_change_is_admin_only_and_audited(client, headers_for, make_user):
    make_user("frank_target", "VIEWER")
    target = client.get("/api/auth/users", headers=headers_for("ADMIN"))
    target_id = next(u["id"] for u in target.json() if u["username"] == "frank_target")
    url = f"/api/auth/users/{target_id}/role"
    assert client.patch(url, json={"role": "ADMIN"}, headers=headers_for("ENGINEER")).status_code == 403
    changed = client.patch(url, json={"role": "AUDITOR"}, headers=headers_for("ADMIN"))
    assert changed.status_code == 200 and changed.json()["role"] == "AUDITOR"
    logs = client.get("/api/audit/logs", params={"action": "ROLE_CHANGE"}, headers=headers_for("AUDITOR"))
    assert any(item["resource"] == "user:frank_target" for item in logs.json()["items"])


def test_admin_cannot_change_own_role(client, headers_for):
    me = client.get("/api/auth/me", headers=headers_for("ADMIN")).json()
    response = client.patch(f"/api/auth/users/{me['id']}/role", json={"role": "VIEWER"},
                            headers=headers_for("ADMIN"))
    assert response.status_code == 400
