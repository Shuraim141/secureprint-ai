from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.blockchain.workflow import WORKFLOW_STEPS

WorkflowAction = Literal[tuple(WORKFLOW_STEPS)]  # type: ignore[valid-type]


class PartCreate(BaseModel):
    design_id: int
    batch: str = Field(min_length=1, max_length=64)
    material: str = Field(min_length=1, max_length=64)
    printer_id: int | None = None


class EventCreate(BaseModel):
    action: WorkflowAction
    status: str = Field(default="COMPLETED", max_length=32)
    payload: dict[str, Any] | None = None


class PartOut(BaseModel):
    id: int
    part_code: str
    design_id: int
    design_code: str | None
    design_hash: str
    batch: str
    material: str
    printer_id: int | None
    manufactured_at: datetime | None
    quality_result: str | None
    status: str
    created_at: datetime


class EventOut(BaseModel):
    event_id: str
    sequence: int
    action: str
    status: str
    actor: str
    timestamp: datetime
    payload: dict[str, Any] | None
    prev_hash: str
    hash: str
    signature: str


class ChainVerificationOut(BaseModel):
    valid: bool
    checked: int
    first_broken_event: int | None
    reason: str | None


class ProvenanceOut(BaseModel):
    part: PartOut
    events: list[EventOut]
    chain_verification: ChainVerificationOut


class AuthenticateOut(BaseModel):
    verdict: str
    part: PartOut | None
    reason: str
    chain_verification: ChainVerificationOut | None = None
