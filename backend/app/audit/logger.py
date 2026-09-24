"""Hash-chained audit logging.

Design notes:
* write_audit commits the caller's session, so pending changes made just before it (for
  example a failed-login counter) are persisted together with the audit record.
* A process-wide lock serialises "read last hash -> insert" so concurrent requests cannot
  fork the chain. This is why the MVP runs a single worker.
  Production: PostgreSQL advisory lock / serialisable transaction, or a Fabric ledger.
"""
import json
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.chain import GENESIS_HASH, ChainVerification, canonical_json, compute_hash, verify_chain
from app.models.security_events import AuditLog
from app.timeutil import iso_utc, utcnow

_chain_lock = threading.Lock()
_SENSITIVE_MARKERS = ("password", "secret", "token", "key", "authorization")


def _redact(details: dict | None) -> dict | None:
    if not details:
        return None
    clean = {}
    for name, value in details.items():
        hidden = any(marker in name.lower() for marker in _SENSITIVE_MARKERS)
        clean[name] = "[REDACTED]" if hidden else value
    # Round-trip through canonical JSON so the hashed and the stored value are identical.
    return json.loads(canonical_json(clean))


def audit_record_fields(entry: AuditLog) -> dict:
    """The exact fields covered by event_hash."""
    return {
        "timestamp": iso_utc(entry.timestamp), "user": entry.user, "action": entry.action,
        "resource": entry.resource, "ip": entry.ip, "result": entry.result,
        "severity": entry.severity, "details": entry.details,
    }


def write_audit(
    db: Session, *, action: str, user: str = "system", resource: str | None = None,
    ip: str | None = None, result: str = "SUCCESS", severity: str = "INFO",
    details: dict | None = None,
) -> AuditLog:
    with _chain_lock:
        last_hash = db.execute(
            select(AuditLog.event_hash).order_by(AuditLog.id.desc()).limit(1)
        ).scalar_one_or_none() or GENESIS_HASH
        entry = AuditLog(
            timestamp=utcnow(), user=user[:64], action=action[:64],
            resource=(resource[:255] if resource else None), ip=ip, result=result,
            severity=severity, details=_redact(details), prev_hash=last_hash, event_hash="",
        )
        entry.event_hash = compute_hash(last_hash, audit_record_fields(entry))
        db.add(entry)
        db.commit()
    return entry


def verify_audit_chain(db: Session) -> ChainVerification:
    rows = db.execute(select(AuditLog).order_by(AuditLog.id)).scalars()
    return verify_chain(
        {"id": r.id, "prev_hash": r.prev_hash, "hash": r.event_hash,
         "record": audit_record_fields(r)}
        for r in rows
    )
