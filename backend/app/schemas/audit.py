from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    user: str
    action: str
    resource: str | None
    ip: str | None
    result: str
    severity: str
    details: dict | None
    prev_hash: str
    event_hash: str


class AuditLogPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AuditLogOut]


class ChainVerificationOut(BaseModel):
    valid: bool
    checked: int
    first_broken_id: int | None
    reason: str | None
