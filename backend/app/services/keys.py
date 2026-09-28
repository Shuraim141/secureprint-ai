"""Settings-bound key provider. Production: return a KMS/HSM-backed KeyProvider here."""
import base64
from functools import lru_cache

from app.config import get_settings
from app.security.crypto import KeyProvider, LocalKeyProvider


class EncryptionNotConfigured(RuntimeError):
    """MASTER_KEY is missing from the environment."""


@lru_cache
def get_key_provider() -> KeyProvider:
    master = get_settings().master_key
    if not master:
        raise EncryptionNotConfigured(
            "Encryption is not configured: set MASTER_KEY in .env (run scripts/init_env.py)"
        )
    return LocalKeyProvider(base64.b64decode(master))
