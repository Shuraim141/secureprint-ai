from pydantic import BaseModel


class ComplianceCounts(BaseModel):
    pass_count: int
    fail_count: int
    unknown_count: int
    total: int


class DashboardSummary(BaseModel):
    """Live counts read from the database on every request (no cached or hardcoded numbers)."""

    designs: int
    active_prints: int
    defects_detected: int
    incidents_open: int
    incidents_total: int
    parts: int
    supply_chain_events: int
    audit_events: int
    compliance: ComplianceCounts
