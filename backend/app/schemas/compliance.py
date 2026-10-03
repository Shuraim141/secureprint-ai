from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ControlOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    framework: str
    control_ref: str
    title: str
    description: str
    status: str
    evidence: str | None
    last_checked: datetime | None


class ComplianceReport(BaseModel):
    generated_at: datetime
    disclaimer: str
    pass_count: int
    fail_count: int
    unknown_count: int
    total: int
    controls: list[ControlOut]
