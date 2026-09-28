import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class FingerprintOut(BaseModel):
    kind: str
    value: str
    meta: dict | None = None


class VersionOut(BaseModel):
    version: int
    original_filename: str
    file_size: int
    sha256: str
    encrypted: bool
    encryption_alg: str | None
    created_by: str
    created_at: datetime
    analysis: dict | None
    fingerprints: list[FingerprintOut]


class FourDFields(BaseModel):
    material_id: str
    material_name: str
    material_class: str
    trigger_type: str
    trigger_temperature_c: float | None = None
    trigger_time_s: float | None = None
    target_state: str
    transformation_profile: dict[str, Any] = {}
    activation_conditions: dict[str, Any] = {}


class FourDProfileIn(FourDFields):
    """4D-printing METADATA record (material, trigger, target state). It describes intended
    behaviour and protects it with a fingerprint; it does not simulate the physics."""

    material_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    material_name: str = Field(min_length=1, max_length=128)
    material_class: str = Field(min_length=1, max_length=64)
    trigger_type: Literal["temperature", "humidity", "light", "magnetic_field",
                          "electric_field", "ph", "time"]
    trigger_temperature_c: float | None = Field(default=None, ge=-100, le=1500)
    trigger_time_s: float | None = Field(default=None, gt=0, le=10_000_000)
    target_state: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate(self):
        if self.trigger_type == "temperature" and self.trigger_temperature_c is None:
            raise ValueError("trigger_temperature_c is required when trigger_type is 'temperature'")
        for name in ("transformation_profile", "activation_conditions"):
            try:
                text = json.dumps(getattr(self, name), allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be plain JSON (no NaN/Infinity)") from exc
            if len(text) > 4096:
                raise ValueError(f"{name} is too large (limit 4096 characters)")
        return self


class FourDProfileOut(FourDFields):
    security_fingerprint: str
    design_version: int
    created_by: str
    created_at: datetime


class FourDVerifyOut(BaseModel):
    intact: bool
    expected: str
    stored: str
    design_version: int
    reason: str


class HistoryEvent(BaseModel):
    time: datetime
    actor: str
    event: str
    detail: str


class DesignSummaryOut(BaseModel):
    id: int
    design_code: str
    name: str
    owner: str
    file_format: str
    current_version: int
    is_4d: bool
    created_at: datetime
    sha256: str
    triangle_count: int | None
    encrypted: bool


class DesignDetailOut(DesignSummaryOut):
    versions: list[VersionOut]
    profile_4d: FourDProfileOut | None
    history: list[HistoryEvent]
    warnings: list[str] = []


class VerifyOut(BaseModel):
    filename: str
    sha256: str
    verdict: str
    headline: str
    reasons: list[str]
    match_type: str | None
    matched_design: dict | None
    checks: dict
    differences: dict | None
    uploaded_analysis: dict | None
    uploaded_geometric_fingerprint: str | None
