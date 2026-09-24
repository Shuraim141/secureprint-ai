"""Quality inspection tables (used from Phase 5)."""
from datetime import datetime

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import UTCDateTime
from app.timeutil import utcnow


class QualityInspection(Base):
    __tablename__ = "quality_inspections"

    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int | None] = mapped_column(ForeignKey("parts.id"), nullable=True)
    print_job_id: Mapped[int | None] = mapped_column(ForeignKey("print_jobs.id"), nullable=True)
    inspector_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    image_sha256: Mapped[str] = mapped_column(String(64), index=True)
    predicted_class: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24))  # normal | defect_detected
    confidence: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(16))
    model_version: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    defects: Mapped[list["Defect"]] = relationship(
        back_populates="inspection", cascade="all, delete-orphan"
    )


class Defect(Base):
    __tablename__ = "defects"

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("quality_inspections.id"), index=True)
    defect_type: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(16))
    region: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    inspection: Mapped[QualityInspection] = relationship(back_populates="defects")
