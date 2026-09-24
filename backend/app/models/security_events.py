"""Security events, incidents and the tamper-evident audit log."""
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.types import UTCDateTime
from app.timeutil import utcnow


class AuditLog(Base):
    """Append-only, hash-chained. event_hash = SHA-256(prev_hash + canonical record)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    user: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(16))  # SUCCESS | FAILURE
    severity: Mapped[str] = mapped_column(String(16), default="INFO")
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), unique=True)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_code: Mapped[str | None] = mapped_column(String(24), unique=True, index=True)  # INC-00042
    incident_type: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(16))
    printer_id: Mapped[int | None] = mapped_column(ForeignKey("printers.id"), nullable=True)
    print_job_id: Mapped[int | None] = mapped_column(ForeignKey("print_jobs.id"), nullable=True)
    action_taken: Mapped[str] = mapped_column(String(64))  # e.g. PRINT_PAUSED (simulated)
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    description: Mapped[str] = mapped_column(Text, default="")
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_code: Mapped[str | None] = mapped_column(String(24), unique=True, index=True)  # EVT-000001
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    source: Mapped[str] = mapped_column(String(64))
    resource: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
