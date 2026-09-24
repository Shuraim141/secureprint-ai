"""3D/4D design tables (used from Phase 4)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import UTCDateTime
from app.timeutil import utcnow


class Design(Base):
    __tablename__ = "designs"

    id: Mapped[int] = mapped_column(primary_key=True)
    design_code: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)  # SP-3D-000001
    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    file_format: Mapped[str] = mapped_column(String(8))  # stl | obj | 3mf
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    is_4d: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    versions: Mapped[list["DesignVersion"]] = relationship(
        back_populates="design", cascade="all, delete-orphan", order_by="DesignVersion.version"
    )
    profile_4d: Mapped[Optional["Design4DProfile"]] = relationship(
        back_populates="design", cascade="all, delete-orphan", uselist=False
    )


class DesignVersion(Base):
    __tablename__ = "design_versions"
    __table_args__ = (UniqueConstraint("design_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    design_id: Mapped[int] = mapped_column(ForeignKey("designs.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    original_filename: Mapped[str] = mapped_column(String(255))  # display only, never used as a path
    storage_key: Mapped[str] = mapped_column(String(128))  # generated name, never user-controlled
    file_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    encryption_alg: Mapped[str | None] = mapped_column(String(32), nullable=True)  # AES-256-GCM
    nonce_b64: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wrapped_key_b64: Mapped[str | None] = mapped_column(Text, nullable=True)  # envelope encryption
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # geometry stats from the parser
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    design: Mapped[Design] = relationship(back_populates="versions")
    fingerprints: Mapped[list["DesignFingerprint"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class DesignFingerprint(Base):
    """kind = sha256 (exact) | geometric (canonical geometry) | watermark (fragile, keyed)."""

    __tablename__ = "design_fingerprints"
    __table_args__ = (UniqueConstraint("design_version_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    design_version_id: Mapped[int] = mapped_column(ForeignKey("design_versions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    value: Mapped[str] = mapped_column(String(128), index=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    version: Mapped[DesignVersion] = relationship(back_populates="fingerprints")


class Design4DProfile(Base):
    """4D-printing METADATA/security record. Not a physical transformation simulation."""

    __tablename__ = "design_4d_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    design_id: Mapped[int] = mapped_column(ForeignKey("designs.id"), unique=True)
    material_id: Mapped[str] = mapped_column(String(64))
    material_name: Mapped[str] = mapped_column(String(128))
    material_class: Mapped[str] = mapped_column(String(64))  # e.g. shape-memory polymer
    trigger_type: Mapped[str] = mapped_column(String(32))  # temperature | humidity | light | ...
    trigger_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    trigger_time_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_state: Mapped[str] = mapped_column(String(64))
    transformation_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    activation_conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    security_fingerprint: Mapped[str] = mapped_column(String(64))  # SHA-256(profile + design hash)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    design: Mapped[Design] = relationship(back_populates="profile_4d")
