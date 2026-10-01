"""Printer telemetry generation (Module F): pure functions, no asyncio/DB, so the scenario
logic is fully unit-testable. manufacturing/simulator.py wraps this in a background task.

Four scenarios, matching the specification exactly:
  NORMAL              - all parameters stay near their safe-range centre
  OVERHEAT            - nozzle temperature climbs steadily past the safe range
  SPEED_SPIKE         - print speed jumps far above the safe range at a fixed tick
  PARAMETER_TAMPERING - several parameters go out of range at once (the broadest attack)

Telemetry fields match the specification: temperature, bed_temperature, speed, flow_rate,
layer, progress, power, timestamp.
"""
import random
from dataclasses import dataclass

from app.ml.process_dataset import SAFE_RANGES

SCENARIOS = ("NORMAL", "OVERHEAT", "SPEED_SPIKE", "PARAMETER_TAMPERING")
DEFAULT_TOTAL_LAYERS = 40
SPEED_SPIKE_AT_TICK = 8


def _centre(name: str) -> float:
    low, high = SAFE_RANGES[name]
    return (low + high) / 2


@dataclass(frozen=True)
class JobParams:
    total_layers: int = DEFAULT_TOTAL_LAYERS
    ticks_per_layer: int = 3  # how many telemetry samples advance one printed layer


def generate_sample(scenario: str, tick: int, params: JobParams, rng: random.Random) -> dict:
    """One telemetry sample for `tick` (0-based, ticks arrive once per second in the real
    simulator). Deterministic given the same rng state, so a fixed seed reproduces a scenario
    exactly -- required for a repeatable exam demonstration."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")

    nozzle = _centre("nozzle_temp_c") + rng.gauss(0, 1.5)
    bed = _centre("bed_temp_c") + rng.gauss(0, 0.8)
    speed = _centre("speed_mm_s") + rng.gauss(0, 3.0)
    flow = _centre("extrusion_rate_pct") + rng.gauss(0, 1.5)

    if scenario == "OVERHEAT":
        nozzle += min(tick * 6.0, 90.0)  # climbs roughly 6C per tick, caps at +90C
    elif scenario == "SPEED_SPIKE":
        if tick >= SPEED_SPIKE_AT_TICK:
            speed += 200.0
    elif scenario == "PARAMETER_TAMPERING":
        if tick >= SPEED_SPIKE_AT_TICK:
            nozzle += 60.0
            bed += 45.0
            speed += 150.0
            flow += 40.0

    total_ticks = params.total_layers * params.ticks_per_layer
    clamped_tick = min(tick, total_ticks)
    layer = min(params.total_layers, clamped_tick // params.ticks_per_layer + 1)
    progress = round(min(100.0, 100.0 * clamped_tick / total_ticks), 1)
    power = round(40.0 + 0.25 * max(0.0, nozzle - 20) + 0.15 * max(0.0, bed - 20) + rng.gauss(0, 2), 1)

    return {
        "tick": tick, "temperature": round(nozzle, 2), "bed_temperature": round(bed, 2),
        "speed": round(max(0.0, speed), 2), "flow_rate": round(max(0.0, flow), 2),
        "layer": int(layer), "total_layers": params.total_layers, "progress": progress,
        "power": max(0.0, power),
    }


def is_complete(sample: dict) -> bool:
    return sample["progress"] >= 100.0
