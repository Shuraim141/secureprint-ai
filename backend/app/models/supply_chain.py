"""Parts and the provenance ledger (used from Phase 6).

Production: LedgerBackend adapter -> Hyperledger Fabric (not deployed in this MVP).
"""
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.types import UTCDateTime
from app.timeutil import utcnow


class Part(Base):
    __tablename__ = "parts"

    id: Mapped[int] = mapped_column(primary_key=True)
    part_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    design_id: Mapped[int] = mapped_column(ForeignKey("designs.id"), index=True)
    design_hash: Mapped[str] = mapped_column(String(64))
    batch: Mapped[str] = mapped_column(String(64))
    printer_id: Mapped[int | None] = mapped_column(ForeignKey("printers.id"), nullable=True)
    material: Mapped[str] = mapped_column(String(64))
    manufactured_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    quality_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="CREATED")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SupplyChainEvent(Base):
    """One link in a hash chain. chain_id groups events (a part code, or DESIGN-<code>)."""

    __tablename__ = "supply_chain_events"
    __table_args__ = (UniqueConstraint("chain_id", "sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    chain_id: Mapped[str] = mapped_column(String(80), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    part_id: Mapped[int | None] = mapped_column(ForeignKey("parts.id"), nullable=True)
    design_id: Mapped[int | None] = mapped_column(ForeignKey("designs.id"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    signature: Mapped[str] = mapped_column(String(160))  # Ed25519, base64
