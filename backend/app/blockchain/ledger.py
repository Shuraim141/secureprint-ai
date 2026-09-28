"""Provenance ledger: a cryptographically linked, Ed25519-signed, append-only event chain.

MVP implementation:
We use a local hash-chained ledger (reusing app/audit/chain.py's primitives, the same
mechanism that protects the audit log) because Hyperledger Fabric requires a substantially
more complex multi-service infrastructure (peers, an orderer, a CA, chaincode) than a local
student environment can reasonably run.

Each event's hash covers the previous event's hash plus its own canonical JSON payload, and
each event is additionally signed with Ed25519 (the ledger's own keypair, deterministically
derived from MASTER_KEY via KeyProvider -- see security/crypto.py). Verification re-derives
every hash AND re-checks every signature, and reports the first broken link.

Production deployment:
This module implements the LedgerBackend interface, so it can be swapped for a Hyperledger
Fabric adapter (chaincode submitting the same event shape) without changing the service layer
(services/supply_chain.py) or the API.

Known limit shared with the audit log: deleting the LAST events in a chain cannot be detected
from the chain alone (nothing after them refers back). Production: periodically anchor each
chain's head hash externally (WORM storage, Fabric, a signed timestamp).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.audit.chain import ChainVerification, compute_hash, verify_chain
from app.security.crypto import KeyProvider

LEDGER_SIGNING_KEY_PURPOSE = "ledger-signing"


@dataclass(frozen=True)
class LedgerEntry:
    event_id: str
    chain_id: str
    sequence: int
    record: dict          # the fields that are hashed/signed (actor, action, status, payload, ...)
    prev_hash: str
    hash: str
    signature_hex: str


class LedgerBackend(ABC):
    """Adapter interface. MVP: LocalHashChainLedger. Production: HyperledgerFabricLedger."""

    @abstractmethod
    def append(self, chain_id: str, sequence: int, record: dict, prev_hash: str) -> LedgerEntry: ...

    @abstractmethod
    def verify_entries(self, entries: list[LedgerEntry]) -> ChainVerification: ...


class LocalHashChainLedger(LedgerBackend):
    def __init__(self, key_provider: KeyProvider):
        seed = key_provider.derive_subkey(LEDGER_SIGNING_KEY_PURPOSE)
        self._signing_key = Ed25519PrivateKey.from_private_bytes(seed)
        self._public_key = self._signing_key.public_key()

    def append(self, chain_id: str, sequence: int, record: dict, prev_hash: str) -> LedgerEntry:
        digest = compute_hash(prev_hash, record)
        signature = self._signing_key.sign(digest.encode("utf-8"))
        return LedgerEntry(
            event_id=f"EVT-{chain_id}-{sequence:04d}", chain_id=chain_id, sequence=sequence,
            record=record, prev_hash=prev_hash, hash=digest, signature_hex=signature.hex(),
        )

    def _verify_signature(self, entry: LedgerEntry) -> bool:
        try:
            self._public_key.verify(bytes.fromhex(entry.signature_hex), entry.hash.encode("utf-8"))
            return True
        except (InvalidSignature, ValueError):
            return False

    def verify_entries(self, entries: list[LedgerEntry]) -> ChainVerification:
        """Hash-chain integrity AND signature validity; reports the first broken link of either kind."""
        hash_result = verify_chain(
            {"id": e.sequence, "prev_hash": e.prev_hash, "hash": e.hash, "record": e.record}
            for e in entries
        )
        if not hash_result.valid:
            return hash_result
        for entry in entries:
            if not self._verify_signature(entry):
                return ChainVerification(
                    False, entry.sequence, entry.sequence,
                    "Ed25519 signature does not match this event's hash (tampered or forged)",
                )
        return ChainVerification(True, len(entries))

    def public_key_hex(self) -> str:
        from cryptography.hazmat.primitives import serialization
        raw = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        return raw.hex()
