"""Security-event records (used by design tamper detection now; incident response in Phase 7)."""
from sqlalchemy.orm import Session

from app.models.security_events import SecurityEvent


def record_security_event(
    db: Session, *, event_type: str, severity: str, source: str, resource: str | None,
    reason: str, response: str | None = None, details: dict | None = None,
) -> SecurityEvent:
    event = SecurityEvent(event_type=event_type, severity=severity, source=source,
                          resource=resource, reason=reason, response=response, details=details)
    db.add(event)
    db.flush()
    event.event_code = f"EVT-{event.id:06d}"
    db.commit()
    return event
