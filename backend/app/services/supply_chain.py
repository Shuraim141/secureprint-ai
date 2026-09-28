"""Supply-chain provenance and part authentication (Module D/E). No HTTP here.

Ledger design (repeated from blockchain/ledger.py for anyone reading only this file):
MVP uses a local cryptographically-linked, Ed25519-signed hash chain because Hyperledger
Fabric is impractical on a student machine. See blockchain/ledger.py for the full rationale
and the LedgerBackend interface that would carry a production migration.
"""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.chain import GENESIS_HASH
from app.blockchain.ledger import LedgerBackend, LedgerEntry
from app.blockchain.workflow import validate_next_action
from app.models import Design, DesignVersion, Part, SupplyChainEvent, User
from app.timeutil import iso_utc, utcnow


class PartNotFoundError(Exception):
    pass


class DuplicatePartCodeError(Exception):
    pass


def _record_for_ledger(*, event_id: str, part_code: str, action: str, actor: str,
                       status: str, timestamp: datetime, payload: dict | None) -> dict:
    return {"event_id": event_id, "part_code": part_code, "action": action, "actor": actor,
            "status": status, "timestamp": iso_utc(timestamp), "payload": payload}


def _chain_events(db: Session, chain_id: str) -> list[SupplyChainEvent]:
    return list(db.execute(
        select(SupplyChainEvent).where(SupplyChainEvent.chain_id == chain_id)
        .order_by(SupplyChainEvent.sequence)
    ).scalars())


def _next_part_code(db: Session) -> str:
    count = db.execute(select(func.count()).select_from(Part)).scalar_one()
    return f"PART-{count + 1:06d}"


def create_part(db: Session, *, design: Design, version: DesignVersion, batch: str,
                material: str, actor: User, ledger: LedgerBackend, printer_id: int | None = None) -> Part:
    """Registers a new part and seeds its provenance chain with DESIGN_CREATED."""
    part = Part(part_code=_next_part_code(db), design_id=design.id, design_hash=version.sha256,
               batch=batch, material=material, printer_id=printer_id, status="CREATED")
    db.add(part)
    db.flush()
    try:
        # append_event() commits the transaction (both the part row and this first event
        # together); on failure, roll back so a half-created part is never left behind.
        append_event(db, part=part, actor=actor, action="DESIGN_CREATED",
                    payload={"design_code": design.design_code, "design_version": version.version,
                             "design_sha256": version.sha256}, ledger=ledger)
    except Exception:
        db.rollback()
        raise
    db.refresh(part)
    return part


def append_event(db: Session, *, part: Part, actor: User, action: str, ledger: LedgerBackend,
                 status: str = "COMPLETED", payload: dict | None = None) -> SupplyChainEvent:
    """Validates workflow order, appends a signed, hash-chained event, updates part.status.
    Raises WorkflowOrderError (mapped to 409 by the API) on an out-of-order request."""
    existing = _chain_events(db, part.part_code)
    last_action = existing[-1].action if existing else None
    validate_next_action(last_action, action)  # raises WorkflowOrderError

    sequence = len(existing) + 1
    prev_hash = existing[-1].hash if existing else GENESIS_HASH
    timestamp = utcnow()
    # The event id is derived from the chain id and sequence, so it is known before hashing and
    # is part of what gets hashed and signed (must match LocalHashChainLedger.append's format).
    event_id = f"EVT-{part.part_code}-{sequence:04d}"
    ledger_record = _record_for_ledger(
        event_id=event_id, part_code=part.part_code, action=action, actor=actor.username,
        status=status, timestamp=timestamp, payload=payload)
    entry: LedgerEntry = ledger.append(part.part_code, sequence, ledger_record, prev_hash)
    if entry.event_id != event_id:  # the two id formats must stay in sync or verification fails
        raise RuntimeError("ledger event id format diverged from the service layer")

    row = SupplyChainEvent(
        event_id=entry.event_id, chain_id=part.part_code, sequence=sequence, part_id=part.id,
        design_id=part.design_id, timestamp=timestamp, actor=actor.username, action=action,
        status=status, payload=payload, prev_hash=prev_hash, hash=entry.hash,
        signature=entry.signature_hex,
    )
    db.add(row)
    part.status = action
    if action == "QUALITY_INSPECTED" and payload and "quality_result" in payload:
        part.quality_result = payload["quality_result"]
    if action == "PRINT_STARTED":
        part.manufactured_at = timestamp
    db.commit()
    db.refresh(row)
    return row


def get_part_by_code(db: Session, part_code: str) -> Part | None:
    return db.execute(select(Part).where(Part.part_code == part_code)).scalar_one_or_none()


def _to_ledger_entries(rows: list[SupplyChainEvent], part_code: str) -> list[LedgerEntry]:
    entries = []
    for row in rows:
        record = _record_for_ledger(
            event_id=row.event_id, part_code=part_code, action=row.action, actor=row.actor,
            status=row.status, timestamp=row.timestamp, payload=row.payload)
        entries.append(LedgerEntry(event_id=row.event_id, chain_id=row.chain_id,
                                   sequence=row.sequence, record=record, prev_hash=row.prev_hash,
                                   hash=row.hash, signature_hex=row.signature))
    return entries


def verify_part_chain(db: Session, part: Part, ledger: LedgerBackend):
    rows = _chain_events(db, part.part_code)
    return ledger.verify_entries(_to_ledger_entries(rows, part.part_code))


def authenticate_part(db: Session, part_code: str, ledger: LedgerBackend) -> dict:
    """AUTHENTIC / TAMPERED / INVALID / UNKNOWN with the real reason -- for Module E."""
    part = get_part_by_code(db, part_code)
    if part is None:
        return {"verdict": "UNKNOWN", "part": None, "reason": f"No part registered as {part_code}"}

    chain_result = verify_part_chain(db, part, ledger)
    if not chain_result.valid:
        return {
            "verdict": "TAMPERED", "part": part_out(db, part),
            "reason": f"Provenance chain integrity failure at event #{chain_result.first_broken_id}: "
                     f"{chain_result.reason}",
            "chain_verification": _chain_out(chain_result),
        }

    design_version = db.execute(select(DesignVersion).where(
        DesignVersion.design_id == part.design_id, DesignVersion.sha256 == part.design_hash
    )).scalar_one_or_none()
    if design_version is None:
        return {
            "verdict": "INVALID", "part": part_out(db, part),
            "reason": "No registered design version matches this part's recorded design hash "
                     "(the design record may have been altered)",
            "chain_verification": _chain_out(chain_result),
        }

    return {
        "verdict": "AUTHENTIC", "part": part_out(db, part),
        "reason": f"Provenance chain intact ({chain_result.checked} events, signatures valid) "
                 f"and design hash matches registered design version {design_version.version}",
        "chain_verification": _chain_out(chain_result),
    }


def _chain_out(result) -> dict:
    return {"valid": result.valid, "checked": result.checked,
           "first_broken_event": result.first_broken_id, "reason": result.reason}


def part_out(db: Session, part: Part) -> dict:
    design = db.get(Design, part.design_id)
    return {
        "id": part.id, "part_code": part.part_code, "design_id": part.design_id,
        "design_code": design.design_code if design else None, "design_hash": part.design_hash,
        "batch": part.batch, "material": part.material, "printer_id": part.printer_id,
        "manufactured_at": part.manufactured_at, "quality_result": part.quality_result,
        "status": part.status, "created_at": part.created_at,
    }


def event_out(row: SupplyChainEvent) -> dict:
    return {
        "event_id": row.event_id, "sequence": row.sequence, "action": row.action,
        "status": row.status, "actor": row.actor, "timestamp": row.timestamp,
        "payload": row.payload, "prev_hash": row.prev_hash, "hash": row.hash,
        "signature": row.signature,
    }


def part_provenance(db: Session, part: Part, ledger: LedgerBackend) -> dict:
    rows = _chain_events(db, part.part_code)
    verification = ledger.verify_entries(_to_ledger_entries(rows, part.part_code))
    return {"part": part_out(db, part), "events": [event_out(r) for r in rows],
           "chain_verification": _chain_out(verification)}
