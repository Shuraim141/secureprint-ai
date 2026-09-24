"""Hash-chain primitives shared by the audit log and (Phase 6) the provenance ledger.

hash_n = SHA-256(hash_{n-1} + canonical_json(record_n)); the first link uses GENESIS_HASH.
Pure functions, no database or framework imports.

Known limit: deleting the LAST records cannot be detected from the chain alone (nothing
follows them). Production: periodically anchor the head hash externally (WORM storage,
Fabric, a signed timestamp).
"""
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass

GENESIS_HASH = "0" * 64


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_hash(prev_hash: str, record: dict) -> str:
    return hashlib.sha256((prev_hash + canonical_json(record)).encode("utf-8")).hexdigest()


@dataclass
class ChainVerification:
    valid: bool
    checked: int
    first_broken_id: int | None = None
    reason: str | None = None


def verify_chain(entries: Iterable[dict]) -> ChainVerification:
    """entries: dicts in chain order with keys id, prev_hash, hash, record.
    Returns the first broken link, or valid=True."""
    expected_prev = GENESIS_HASH
    checked = 0
    for entry in entries:
        checked += 1
        if entry["prev_hash"] != expected_prev:
            return ChainVerification(
                False, checked, entry["id"],
                "Previous-hash link broken (a record was deleted, inserted or reordered)",
            )
        if compute_hash(entry["prev_hash"], entry["record"]) != entry["hash"]:
            return ChainVerification(
                False, checked, entry["id"], "Record contents do not match the stored hash"
            )
        expected_prev = entry["hash"]
    return ChainVerification(True, checked)
