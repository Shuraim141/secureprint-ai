"""Pure-logic tests for the provenance ledger (hash chain + Ed25519 signatures) and workflow
order enforcement. No web framework or database -- these run everywhere."""
import copy

from app.audit.chain import GENESIS_HASH
from app.blockchain.ledger import LedgerEntry, LocalHashChainLedger
from app.blockchain.workflow import (
    FIRST_STEP,
    TERMINAL_STEP,
    WORKFLOW_STEPS,
    WorkflowOrderError,
    next_expected_action,
    validate_next_action,
)
from app.security.crypto import LocalKeyProvider

KEY = bytes(range(32))
OTHER_KEY = bytes(range(32, 64))


def raises(exc_type, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except exc_type as error:
        return error
    raise AssertionError(f"expected {exc_type.__name__}")


def build_chain(ledger, part_code="PART-000001"):
    entries, prev = [], GENESIS_HASH
    for i, action in enumerate(WORKFLOW_STEPS, start=1):
        record = {"event_id": f"EVT-{part_code}-{i:04d}", "part_code": part_code,
                  "action": action, "actor": "engineer1", "status": "COMPLETED", "payload": None}
        entry = ledger.append(part_code, i, record, prev)
        entries.append(entry)
        prev = entry.hash
    return entries


# ---------------- workflow order ----------------
def test_workflow_order_enforced():
    assert next_expected_action(None) == FIRST_STEP == "DESIGN_CREATED"
    assert next_expected_action("SHIPPED") == "RECEIVED" == TERMINAL_STEP
    for i in range(len(WORKFLOW_STEPS) - 1):
        assert next_expected_action(WORKFLOW_STEPS[i]) == WORKFLOW_STEPS[i + 1]
    raises(WorkflowOrderError, next_expected_action, "RECEIVED")
    raises(WorkflowOrderError, validate_next_action, "DESIGN_CREATED", "SHIPPED")
    raises(WorkflowOrderError, validate_next_action, None, "CERTIFIED")
    validate_next_action(None, "DESIGN_CREATED")  # must not raise
    validate_next_action("SLICED", "PRINT_STARTED")  # must not raise


# ---------------- ledger: valid chain ----------------
def test_full_workflow_chain_is_valid_and_signed():
    ledger = LocalHashChainLedger(LocalKeyProvider(KEY))
    entries = build_chain(ledger)
    assert len(entries) == len(WORKFLOW_STEPS) == 9
    result = ledger.verify_entries(entries)
    assert result.valid and result.checked == 9
    for entry in entries:
        assert len(entry.signature_hex) == 128  # 64-byte Ed25519 signature, hex-encoded
        assert entry.hash != entry.prev_hash


def test_empty_chain_is_valid():
    ledger = LocalHashChainLedger(LocalKeyProvider(KEY))
    result = ledger.verify_entries([])
    assert result.valid and result.checked == 0


# ---------------- ledger: tamper detection ----------------
def test_detects_tampered_record_content():
    ledger = LocalHashChainLedger(LocalKeyProvider(KEY))
    entries = build_chain(ledger)
    tampered = copy.deepcopy(entries)
    tampered[3] = LedgerEntry(**{**tampered[3].__dict__,
                                 "record": {**tampered[3].record, "actor": "attacker"}})
    result = ledger.verify_entries(tampered)
    assert not result.valid and result.first_broken_id == 4  # sequence 4 = PRINT_STARTED
    assert "contents" in result.reason.lower()


def test_detects_forged_signature_with_matching_hash():
    """Isolates the Ed25519 check: hash/prev_hash/record all untouched, only the signature
    bytes are swapped for another event's signature."""
    ledger = LocalHashChainLedger(LocalKeyProvider(KEY))
    entries = build_chain(ledger)
    tampered = copy.deepcopy(entries)
    tampered[5] = LedgerEntry(**{**tampered[5].__dict__, "signature_hex": entries[2].signature_hex})
    result = ledger.verify_entries(tampered)
    assert not result.valid
    assert "signature" in result.reason.lower()


def test_detects_deleted_middle_event():
    ledger = LocalHashChainLedger(LocalKeyProvider(KEY))
    entries = build_chain(ledger)
    tampered = entries[:4] + entries[5:]  # remove sequence 5 (QUALITY_INSPECTED)
    result = ledger.verify_entries(tampered)
    assert not result.valid
    assert "link" in result.reason.lower()


def test_events_signed_by_a_different_key_are_rejected():
    """A different ledger (different derived signing key) cannot forge a valid signature that
    the original ledger's public key will accept."""
    ledger = LocalHashChainLedger(LocalKeyProvider(KEY))
    attacker_ledger = LocalHashChainLedger(LocalKeyProvider(OTHER_KEY))
    entries = build_chain(ledger)
    forged_record = {**entries[3].record, "actor": "attacker"}
    forged = attacker_ledger.append("PART-000001", 4, forged_record, entries[2].hash)
    tampered = entries[:3] + [forged] + entries[4:]
    result = ledger.verify_entries(tampered)  # verified against the ORIGINAL ledger's public key
    assert not result.valid


def test_same_seed_produces_the_same_signing_key_deterministically():
    """No keypair file is stored; the signing key re-derives from MASTER_KEY every time the
    app starts, so two independently constructed ledgers with the same key must interoperate."""
    ledger_a = LocalHashChainLedger(LocalKeyProvider(KEY))
    ledger_b = LocalHashChainLedger(LocalKeyProvider(KEY))
    assert ledger_a.public_key_hex() == ledger_b.public_key_hex()
    entries = build_chain(ledger_a)
    assert ledger_b.verify_entries(entries).valid  # ledger_b can verify ledger_a's signatures
