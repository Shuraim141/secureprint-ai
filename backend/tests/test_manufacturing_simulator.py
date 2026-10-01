"""Pure-logic and asyncio tests for the G-code analyzer, telemetry generator, anomaly detector
and printer simulator. No web framework or database -- wraps async code in asyncio.run() so no
pytest-asyncio dependency is needed."""
import asyncio
import random

from app.manufacturing.anomaly import detect_anomaly
from app.manufacturing.mes import LocalMESSimulator
from app.manufacturing.simulator import PrinterSimulatorRegistry
from app.manufacturing.telemetry import JobParams, generate_sample, is_complete
from app.ml.quality_model import ModelNotTrainedError

# The interaction between the threshold layer and a REAL trained Isolation Forest is already
# covered by app/ml's own tests (test_quality_ml.py); here we only test the short-circuit /
# fallback INTEGRATION LOGIC in anomaly.py, using stub models rather than retraining one.


def run(coro):
    return asyncio.run(coro)


def raises(exc_type, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except exc_type as error:
        return error
    raise AssertionError(f"expected {exc_type.__name__}")


# ---------------- telemetry ----------------
def test_normal_scenario_never_exceeds_safe_ranges_over_a_full_job():
    params, rng = JobParams(), random.Random(42)
    for tick in range(params.total_layers * params.ticks_per_layer + 2):
        sample = generate_sample("NORMAL", tick, params, rng)
        assert not detect_anomaly(sample).anomaly, f"NORMAL flagged at tick {tick}: {sample}"


def test_attack_scenarios_are_eventually_flagged():
    params = JobParams()
    for scenario in ("OVERHEAT", "SPEED_SPIKE", "PARAMETER_TAMPERING"):
        rng = random.Random(42)
        assert any(detect_anomaly(generate_sample(scenario, t, params, rng)).anomaly
                  for t in range(20)), scenario


def test_telemetry_determinism_and_progress_completion():
    params = JobParams(total_layers=3, ticks_per_layer=2)
    a = generate_sample("NORMAL", 2, params, random.Random(5))
    b = generate_sample("NORMAL", 2, params, random.Random(5))
    assert a == b
    last = None
    for t in range(params.total_layers * params.ticks_per_layer + 3):
        last = generate_sample("NORMAL", t, params, random.Random(5))
    assert is_complete(last) and last["layer"] == params.total_layers


def test_unknown_scenario_rejected():
    raises(ValueError, generate_sample, "MELTDOWN", 0, JobParams(), random.Random(1))


# ---------------- anomaly detector ----------------
def test_threshold_reason_strings_are_specific():
    result = detect_anomaly({"temperature": 280.0, "bed_temperature": 60.0, "speed": 50.0,
                             "flow_rate": 100.0})
    assert result.anomaly and result.risk == "HIGH" and result.method == "threshold"
    assert "Nozzle temperature" in result.reasons[0] and "280.0" in result.reasons[0]


def test_isolation_forest_layer_falls_back_gracefully_when_untrained():
    class Untrained:
        def predict(self, x):
            raise ModelNotTrainedError("no model")
    normal = {"temperature": 205.0, "bed_temperature": 60.0, "speed": 50.0, "flow_rate": 100.0}
    result = detect_anomaly(normal, process_model=Untrained())
    assert not result.anomaly  # must not crash, must not falsely flag


def test_isolation_forest_layer_only_runs_when_thresholds_pass():
    calls = []
    class Spy:
        def predict(self, x):
            calls.append(x)
            raise ModelNotTrainedError("stop here")
    detect_anomaly({"temperature": 280.0, "bed_temperature": 60.0, "speed": 50.0,
                    "flow_rate": 100.0}, process_model=Spy())
    assert calls == []  # threshold breach short-circuits before the model is even called


# ---------------- MES simulator ----------------
def test_mes_simulator_lifecycle():
    mes = LocalMESSimulator()
    job = mes.submit_job(print_job_id=1)
    assert job.mes_job_id == "MES-000001" and job.status == "QUEUED"
    assert mes.get_job_status(job.mes_job_id).print_job_id == 1
    assert mes.get_job_status("MES-999999") is None
    updated = mes.update_status(job.mes_job_id, "IN_PROGRESS")
    assert updated.status == "IN_PROGRESS"
    assert mes.update_status("MES-999999", "COMPLETED") is None


# ---------------- printer simulator (asyncio) ----------------
def test_normal_job_completes_with_no_anomalies():
    async def scenario():
        registry = PrinterSimulatorRegistry()
        calls = []

        async def on_tick(job, sample, result):
            calls.append(result.anomaly)

        job = registry.start(1, 100, "NORMAL", tick_seconds=0.01, seed=42, on_tick=on_tick)
        job.params = JobParams(total_layers=3, ticks_per_layer=2)
        await asyncio.sleep(0.2)
        return job, calls

    job, calls = run(scenario())
    assert job.state == "COMPLETED"
    assert len(calls) >= 6 and not any(calls)


def test_anomaly_triggers_pause_and_stops_ticking():
    async def scenario():
        registry = PrinterSimulatorRegistry()
        anomaly_seen = asyncio.Event()
        ticks = {"n": 0}

        async def on_tick(job, sample, result):
            ticks["n"] += 1
            if result.anomaly and not anomaly_seen.is_set():
                anomaly_seen.set()
                registry.pause(job.printer_id)

        job = registry.start(2, 200, "OVERHEAT", tick_seconds=0.01, seed=42, on_tick=on_tick)
        await asyncio.wait_for(anomaly_seen.wait(), timeout=2.0)
        await asyncio.sleep(0.05)
        ticks_at_pause = ticks["n"]
        await asyncio.sleep(0.1)
        return job, ticks_at_pause, ticks["n"]

    job, at_pause, after = run(scenario())
    assert job.state == "PAUSED"
    assert after == at_pause  # no further ticks once paused


def test_duplicate_start_is_rejected():
    async def scenario():
        registry = PrinterSimulatorRegistry()

        async def noop(job, sample, result):
            pass

        registry.start(5, 1, "NORMAL", tick_seconds=1.0, seed=1, on_tick=noop)
        error = None
        try:
            registry.start(5, 2, "NORMAL", tick_seconds=1.0, seed=1, on_tick=noop)
        except RuntimeError as exc:
            error = exc
        registry.stop(5)
        return error

    error = run(scenario())
    assert error is not None and "already" in str(error)


def test_stop_cancels_the_running_task():
    async def scenario():
        registry = PrinterSimulatorRegistry()

        async def noop(job, sample, result):
            pass

        job = registry.start(9, 1, "NORMAL", tick_seconds=1.0, seed=1, on_tick=noop)
        registry.stop(9)
        await asyncio.sleep(0.05)
        return registry, job

    registry, job = run(scenario())
    assert (job.task.cancelled() or job.task.done()) and not registry.is_running(9)


def test_a_tick_that_raises_unexpectedly_stops_cleanly_with_an_error_state():
    """A model that raises something other than ModelNotTrainedError must not silently kill
    the background task (visible only as "Task exception was never retrieved" in the server
    log, with the printer frozen and no incident ever recorded) -- it must stop cleanly with
    job.state == "ERROR" and the task itself must not raise."""
    class BrokenModel:
        def predict(self, x):
            raise RuntimeError("simulated unexpected failure")

    async def scenario():
        registry = PrinterSimulatorRegistry()

        async def on_tick(job, sample, result):
            pass

        job = registry.start(11, 1, "NORMAL", tick_seconds=0.01, seed=1, on_tick=on_tick,
                             process_model=BrokenModel())
        await job.task  # any unhandled exception in the task would raise here
        return job

    job = run(scenario())
    assert job.state == "ERROR"
    assert job.error == "simulated unexpected failure"


def test_latest_telemetry_returns_bounded_recent_samples():
    async def scenario():
        registry = PrinterSimulatorRegistry()

        async def noop(job, sample, result):
            pass

        job = registry.start(3, 1, "NORMAL", tick_seconds=0.01, seed=1, on_tick=noop)
        job.params = JobParams(total_layers=2, ticks_per_layer=2)
        await asyncio.sleep(0.15)
        return registry

    registry = run(scenario())
    samples = registry.latest_telemetry(3, limit=2)
    assert len(samples) <= 2
    assert registry.latest_telemetry(999) == []  # unknown printer -> empty, not an error
