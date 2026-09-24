"""Pure-logic unit tests (no web framework, no database). Deliberately free of fixtures."""
import copy
from datetime import datetime, timedelta, timezone

import jwt

from app.audit.chain import GENESIS_HASH, compute_hash, verify_chain
from app.hardware import choose_profile_name, get_hardware_profile
from app.security.rbac import ROLE_PERMISSIONS, Permission, RoleName, has_permission
from app.security.tokens import TokenError, create_access_token, decode_access_token

SECRET = "unit-test-secret-" + "abcdefghij" * 3


def _build_chain(n=5):
    entries, prev = [], GENESIS_HASH
    for i in range(1, n + 1):
        record = {"action": f"EVENT_{i}", "user": "alice", "details": {"n": i}}
        digest = compute_hash(prev, record)
        entries.append({"id": i, "prev_hash": prev, "hash": digest, "record": record})
        prev = digest
    return entries


def test_chain_valid_and_empty():
    assert verify_chain(_build_chain()).valid
    assert verify_chain([]).valid


def test_chain_detects_modified_record():
    entries = _build_chain()
    entries[2]["record"]["action"] = "TAMPERED"
    result = verify_chain(entries)
    assert not result.valid and result.first_broken_id == 3
    assert "contents" in result.reason


def test_chain_detects_deleted_record():
    entries = _build_chain()
    del entries[2]
    result = verify_chain(entries)
    assert not result.valid and result.first_broken_id == 4
    assert "link" in result.reason


def test_chain_detects_reordering():
    entries = _build_chain()
    entries[1], entries[2] = entries[2], entries[1]
    assert not verify_chain(entries).valid


def test_chain_detects_recomputed_hash_without_relinking():
    entries = copy.deepcopy(_build_chain())
    entries[1]["record"]["user"] = "mallory"
    entries[1]["hash"] = compute_hash(entries[1]["prev_hash"], entries[1]["record"])
    result = verify_chain(entries)  # attacker fixed record 2's hash, but record 3 still points at old
    assert not result.valid and result.first_broken_id == 3


def test_token_roundtrip():
    token, jti, exp = create_access_token(subject="7", role="ENGINEER", secret=SECRET,
                                          algorithm="HS256", expires_minutes=5)
    claims = decode_access_token(token, secret=SECRET, algorithm="HS256")
    assert claims["sub"] == "7" and claims["jti"] == jti and claims["type"] == "access"
    assert exp > datetime.now(timezone.utc)


def _expect_token_error(token, secret=SECRET):
    try:
        decode_access_token(token, secret=secret, algorithm="HS256")
    except TokenError:
        return
    raise AssertionError("token should have been rejected")


def test_token_rejections():
    now = datetime.now(timezone.utc)
    base = {"sub": "1", "jti": "abc", "type": "access", "iat": now, "exp": now + timedelta(minutes=5)}
    _expect_token_error(jwt.encode({**base, "exp": now - timedelta(minutes=1)}, SECRET, "HS256"))
    _expect_token_error(jwt.encode(base, "another-secret-" + "z" * 40, "HS256"))
    _expect_token_error(jwt.encode(base, "", algorithm="none"))
    _expect_token_error(jwt.encode({**base, "type": "refresh"}, SECRET, "HS256"))
    _expect_token_error("not.a.jwt")
    good, _, _ = create_access_token(subject="1", role="X", secret=SECRET, algorithm="HS256",
                                     expires_minutes=5)
    header, payload, signature = good.split(".")
    _expect_token_error(f"{header}.{payload}x.{signature}")


def test_rbac_matrix():
    assert set(ROLE_PERMISSIONS) == {r.value for r in RoleName}
    assert all(has_permission("ADMIN", p) for p in Permission)
    assert not has_permission("VIEWER", Permission.DESIGN_UPLOAD)
    assert not has_permission("ENGINEER", Permission.AUDIT_VIEW)
    assert not has_permission("ENGINEER", Permission.USER_MANAGE)
    assert has_permission("AUDITOR", Permission.AUDIT_VIEW)
    assert not has_permission("AUDITOR", Permission.DESIGN_UPLOAD)
    assert has_permission("QUALITY_INSPECTOR", Permission.QUALITY_INSPECT)
    assert not has_permission("SUPPLY_CHAIN", Permission.QUALITY_INSPECT)
    assert not has_permission("NO_SUCH_ROLE", Permission.DASHBOARD_VIEW)


def test_hardware_profile_selection():
    assert choose_profile_name(1, 3.9) == "low"
    assert choose_profile_name(2, 16) == "low"
    assert choose_profile_name(4, 8) == "standard"
    assert choose_profile_name(4, None) == "standard"
    assert choose_profile_name(8, 32) == "high"
    assert choose_profile_name(8, 8) == "standard"
    forced = get_hardware_profile("high")
    assert forced.name == "high" and forced.ml_image_size == 128
    try:
        get_hardware_profile("bogus")
    except ValueError:
        return
    raise AssertionError("unknown profile should raise")
