"""AES-256-GCM envelope encryption. Uses the `cryptography` library only; no custom crypto.

Each file gets its own random 256-bit data key (DEK). The DEK is wrapped (encrypted) by the
key provider. Both layers are AES-256-GCM with a fresh random 96-bit nonce and bind an
"AAD" context (the storage key) so a ciphertext cannot be swapped between records.

MVP: LocalKeyProvider holds the master key from .env.
Production: implement KeyProvider with AWS KMS / Azure Key Vault / HashiCorp Vault / an HSM;
the rest of the application does not change.
"""
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ALGORITHM = "AES-256-GCM"
_NONCE_BYTES = 12


class CryptoError(Exception):
    """Decryption/authentication failed (wrong key, wrong context, or tampered data)."""


class KeyProvider(ABC):
    @abstractmethod
    def wrap_key(self, data_key: bytes, aad: bytes) -> bytes: ...

    @abstractmethod
    def unwrap_key(self, wrapped: bytes, aad: bytes) -> bytes: ...

    @abstractmethod
    def derive_subkey(self, purpose: str) -> bytes:
        """Purpose-separated 32-byte key (e.g. for watermarks) derived from the master key."""


class LocalKeyProvider(KeyProvider):
    def __init__(self, master_key: bytes):
        if len(master_key) != 32:
            raise ValueError("master key must be exactly 32 bytes")
        self._master = master_key

    def wrap_key(self, data_key: bytes, aad: bytes) -> bytes:
        nonce = os.urandom(_NONCE_BYTES)
        return nonce + AESGCM(self._master).encrypt(nonce, data_key, aad)

    def unwrap_key(self, wrapped: bytes, aad: bytes) -> bytes:
        try:
            return AESGCM(self._master).decrypt(wrapped[:_NONCE_BYTES], wrapped[_NONCE_BYTES:], aad)
        except InvalidTag as exc:
            raise CryptoError("Data key could not be unwrapped (wrong master key or tampering)") from exc

    def derive_subkey(self, purpose: str) -> bytes:
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                    info=b"secureprint:" + purpose.encode("utf-8")).derive(self._master)


@dataclass(frozen=True)
class EncryptedBlob:
    ciphertext: bytes   # includes the 16-byte GCM authentication tag
    nonce: bytes
    wrapped_key: bytes


def encrypt_bytes(plaintext: bytes, *, aad: bytes, key_provider: KeyProvider) -> EncryptedBlob:
    data_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, aad)
    return EncryptedBlob(ciphertext, nonce, key_provider.wrap_key(data_key, aad))


def decrypt_bytes(ciphertext: bytes, *, nonce: bytes, wrapped_key: bytes, aad: bytes,
                  key_provider: KeyProvider) -> bytes:
    data_key = key_provider.unwrap_key(wrapped_key, aad)
    try:
        return AESGCM(data_key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise CryptoError("Stored file failed its integrity check (tampered or corrupted)") from exc
