"""Compliance controls (technical support only, not certification) and stored ML metrics."""
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.types import UTCDateTime
from app.timeutil import utcnow


class ComplianceControl(Base):
    __tablename__ = "compliance_controls"
    __table_args__ = (UniqueConstraint("framework", "control_ref"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    framework: Mapped[str] = mapped_column(String(32))  # ISO9001 | ISO_ASTM_52900 | NIST
    control_ref: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")  # PASS | FAIL | UNKNOWN
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class MLModelMetrics(Base):
    """Real metrics written by the training scripts and read by the UI. Never hardcoded."""

    __tablename__ = "ml_model_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(64), index=True)
    trained_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    dataset_description: Mapped[str] = mapped_column(Text)
    n_train: Mapped[int] = mapped_column(Integer)
    n_validation: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict] = mapped_column(JSON)
    disclaimer: Mapped[str] = mapped_column(
        Text,
        default=(
            "Metrics are based on the supplied demonstration/synthetic dataset and do not "
            "represent industrial validation."
        ),
    )
    artifact_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
