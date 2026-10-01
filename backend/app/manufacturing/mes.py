"""Manufacturing Execution System integration (Module K): an abstract interface plus a local
in-memory simulator, because no real industrial MES is available to a student.

Production deployment:
Implement MESAdapter against the site's real MES (e.g. via its REST/OPC-UA API) as
RealMESAdapter; the rest of the application (services/manufacturing.py) does not change.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.timeutil import utcnow


@dataclass
class MESJobStatus:
    mes_job_id: str
    print_job_id: int
    status: str  # QUEUED | IN_PROGRESS | COMPLETED | FAILED
    submitted_at: datetime
    updated_at: datetime


class MESAdapter(ABC):
    @abstractmethod
    def submit_job(self, print_job_id: int) -> MESJobStatus: ...

    @abstractmethod
    def get_job_status(self, mes_job_id: str) -> MESJobStatus | None: ...

    @abstractmethod
    def update_status(self, mes_job_id: str, status: str) -> MESJobStatus | None: ...


class LocalMESSimulator(MESAdapter):
    """In-memory job queue. Not persisted: this is a simulator standing in for a real MES,
    not a system of record -- PrintJob in the database remains the source of truth."""

    def __init__(self):
        self._jobs: dict[str, MESJobStatus] = {}
        self._counter = 0

    def submit_job(self, print_job_id: int) -> MESJobStatus:
        self._counter += 1
        mes_job_id = f"MES-{self._counter:06d}"
        now = utcnow()
        status = MESJobStatus(mes_job_id, print_job_id, "QUEUED", now, now)
        self._jobs[mes_job_id] = status
        return status

    def get_job_status(self, mes_job_id: str) -> MESJobStatus | None:
        return self._jobs.get(mes_job_id)

    def update_status(self, mes_job_id: str, status: str) -> MESJobStatus | None:
        job = self._jobs.get(mes_job_id)
        if job is None:
            return None
        job.status = status
        job.updated_at = utcnow()
        return job


_simulator = LocalMESSimulator()


def get_mes_adapter() -> MESAdapter:
    """Process-wide singleton, matching the in-memory printer registry's lifetime."""
    return _simulator
