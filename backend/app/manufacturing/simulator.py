"""Printer simulator orchestration (Module F): a background asyncio task per running print job.

MVP implementation:
We simulate telemetry in-process because OctoPrint/Klipper normally require a physical printer
or a controller board, neither of which is available to a student. The simulator implements
the same shape of interface (start/pause/stop, poll telemetry) that a future PrinterAdapter for
OctoPrint/Klipper would implement, so the rest of the application would not need to change.

State is kept in memory per running job (an asyncio task plus a bounded telemetry buffer), not
persisted per-tick to the database: only anomaly-triggering samples and the resulting security
records are persisted, which is what an examiner or auditor actually needs to see. Production:
a time-series store (e.g. a dedicated telemetry table or InfluxDB) for full history.
"""
import asyncio
import logging
import random
from collections import deque
from dataclasses import dataclass, field

from app.manufacturing.anomaly import AnomalyResult, detect_anomaly
from app.manufacturing.telemetry import JobParams, SCENARIOS, generate_sample, is_complete

TELEMETRY_BUFFER_SIZE = 120  # ~2 minutes at 1 tick/second


@dataclass
class RunningJob:
    print_job_id: int
    printer_id: int
    scenario: str
    tick: int = 0
    state: str = "RUNNING"  # RUNNING | PAUSED | COMPLETED | STOPPED
    rng: random.Random = field(default_factory=lambda: random.Random())
    params: JobParams = field(default_factory=JobParams)
    telemetry: deque = field(default_factory=lambda: deque(maxlen=TELEMETRY_BUFFER_SIZE))
    latest_anomaly: AnomalyResult | None = None
    process_model: object | None = None
    task: asyncio.Task | None = None
    error: str | None = None  # set if a tick raised unexpectedly; the loop still stops safely


class PrinterSimulatorRegistry:
    """Process-wide registry of running simulated print jobs, keyed by printer_id. One printer
    runs at most one job at a time. Not thread-safe across multiple worker processes -- see
    hardware.py's note on why the MVP always runs a single uvicorn worker."""

    def __init__(self):
        self._jobs: dict[int, RunningJob] = {}

    def is_running(self, printer_id: int) -> bool:
        job = self._jobs.get(printer_id)
        return job is not None and job.state == "RUNNING"

    def get(self, printer_id: int) -> RunningJob | None:
        return self._jobs.get(printer_id)

    def start(self, printer_id: int, print_job_id: int, scenario: str, tick_seconds: float,
             seed: int | None, on_tick, process_model=None) -> RunningJob:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario}")
        if self.is_running(printer_id):
            raise RuntimeError(f"Printer {printer_id} already has a running job")
        job = RunningJob(print_job_id=print_job_id, printer_id=printer_id, scenario=scenario,
                         rng=random.Random(seed), process_model=process_model)
        job.task = asyncio.create_task(self._run(job, tick_seconds, on_tick))
        self._jobs[printer_id] = job
        return job

    async def _run(self, job: RunningJob, tick_seconds: float, on_tick) -> None:
        try:
            while job.state == "RUNNING":
                try:
                    sample = generate_sample(job.scenario, job.tick, job.params, job.rng)
                    result = detect_anomaly(sample, process_model=job.process_model)
                    job.latest_anomaly = result
                    job.telemetry.append({**sample, "anomaly": result.anomaly, "risk": result.risk})
                    await on_tick(job, sample, result)  # persists anomalies, may call job.pause()
                except Exception as exc:  # a single bad tick must never silently kill the job
                    job.state, job.error = "ERROR", str(exc)
                    logging.getLogger("secureprint").error(
                        "printer simulator tick failed", exc_info=exc,
                        extra={"ctx": {"printer_id": job.printer_id, "tick": job.tick}})
                    break
                if job.state != "RUNNING":
                    break
                if is_complete(sample):
                    job.state = "COMPLETED"
                    break
                job.tick += 1
                await asyncio.sleep(tick_seconds)
        except asyncio.CancelledError:
            job.state = "STOPPED"
            raise

    def pause(self, printer_id: int) -> RunningJob | None:
        job = self._jobs.get(printer_id)
        if job is not None and job.state == "RUNNING":
            job.state = "PAUSED"
        return job

    def stop(self, printer_id: int) -> RunningJob | None:
        job = self._jobs.pop(printer_id, None)
        if job is not None and job.task is not None and not job.task.done():
            job.task.cancel()
        return job

    def latest_telemetry(self, printer_id: int, limit: int = 20) -> list[dict]:
        job = self._jobs.get(printer_id)
        if job is None:
            return []
        return list(job.telemetry)[-limit:]


registry = PrinterSimulatorRegistry()
