"""Printers, print jobs, G-code analyses (used from Phase 7)."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.types import UTCDateTime
from app.timeutil import utcnow


class Printer(Base):
    __tablename__ = "printers"

    id: Mapped[int] = mapped_column(primary_key=True)
    printer_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    # simulator now; Production: octoprint | klipper adapters (PrinterAdapter interface)
    adapter: Mapped[str] = mapped_column(String(32), default="simulator")
    state: Mapped[str] = mapped_column(String(24), default="idle")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PrintJob(Base):
    __tablename__ = "print_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_code: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id"), index=True)
    design_id: Mapped[int | None] = mapped_column(ForeignKey("designs.id"), nullable=True)
    part_id: Mapped[int | None] = mapped_column(ForeignKey("parts.id"), nullable=True)
    started_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    scenario: Mapped[str] = mapped_column(String(32), default="NORMAL")
    state: Mapped[str] = mapped_column(String(24), default="queued")
    suspicious: Mapped[bool] = mapped_column(Boolean, default=False)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class GCodeAnalysis(Base):
    __tablename__ = "gcode_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    analyzed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    safe: Mapped[bool] = mapped_column(Boolean)
    risk: Mapped[str] = mapped_column(String(16))
    findings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
