"""Password hashing with Argon2id (argon2-cffi defaults follow the RFC 9106 low-memory profile)."""
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()
_dummy_hash: str | None = None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def burn_verification_time(password: str) -> None:
    """Run a real Argon2 verification against a dummy hash so 'unknown user' takes about as
    long as 'wrong password' (reduces username enumeration through timing)."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = _hasher.hash("timing-equalisation-dummy")
    verify_password(_dummy_hash, password)
