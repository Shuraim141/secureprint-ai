from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.manufacturing.telemetry import SCENARIOS

Scenario = Literal[tuple(SCENARIOS)]  # type: ignore[valid-type]


class PrinterOut(BaseModel):
    id: int
    printer_code: str
    name: str
    adapter: str
    db_state: str
    simulator_state: str
    scenario: str | None
    current_job_id: int | None


class StartPrintIn(BaseModel):
    scenario: Scenario
    seed: int | None = Field(default=None, ge=0, le=2_000_000_000)


class TelemetrySample(BaseModel):
    tick: int
    temperature: float
    bed_temperature: float
    speed: float
    flow_rate: float
    layer: int
    total_layers: int
    progress: float
    power: float
    anomaly: bool
    risk: str


class TelemetryOut(BaseModel):
    printer_id: int
    simulator_state: str
    samples: list[TelemetrySample]


class GCodeFinding(BaseModel):
    line: int
    severity: str
    code: str
    message: str


class GCodeAnalysisOut(BaseModel):
    id: int
    filename: str
    sha256: str
    safe: bool
    risk: str
    findings: list[GCodeFinding]
    stats: dict
    created_at: datetime


class IncidentOut(BaseModel):
    id: int
    incident_code: str | None
    incident_type: str
    severity: str
    printer_id: int | None
    print_job_id: int | None
    action_taken: str
    status: str
    description: str
    opened_at: datetime
    resolved_at: datetime | None


class IncidentPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[IncidentOut]
