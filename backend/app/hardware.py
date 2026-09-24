"""Hardware detection and resource profiles (standard library only).

The MVP must run on a student laptop, so ML sizes, simulator frequency and SQLite
cache adapt to the machine. Override with HARDWARE_PROFILE=low|standard|high.

Worker count is deliberately NOT part of the profile: the printer simulator and the
audit hash-chain lock live inside one process, so the MVP always runs 1 uvicorn worker.
Production: PostgreSQL + an external job runner remove this restriction.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class HardwareProfile:
    name: str
    cpu_cores: int
    ram_gb: float | None
    simulator_tick_seconds: float
    ml_image_size: int
    rf_n_estimators: int
    max_training_samples_per_class: int
    sqlite_cache_kb: int


_PROFILES = {
    "low": dict(simulator_tick_seconds=2.0, ml_image_size=64, rf_n_estimators=50,
                max_training_samples_per_class=80, sqlite_cache_kb=2000),
    "standard": dict(simulator_tick_seconds=1.0, ml_image_size=96, rf_n_estimators=100,
                     max_training_samples_per_class=150, sqlite_cache_kb=8000),
    "high": dict(simulator_tick_seconds=0.5, ml_image_size=128, rf_n_estimators=200,
                 max_training_samples_per_class=300, sqlite_cache_kb=32000),
}


def detect_hardware() -> tuple[int, float | None]:
    """Return (usable CPU cores, total RAM in GB or None if unknown)."""
    try:
        cores = len(os.sched_getaffinity(0))
    except AttributeError:
        cores = os.cpu_count() or 1
    ram_gb = None
    try:
        ram_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
    except (ValueError, OSError, AttributeError):
        pass  # Windows: unknown -> profile chosen by cores only
    return cores, ram_gb


def choose_profile_name(cores: int, ram_gb: float | None) -> str:
    if cores <= 2 or (ram_gb is not None and ram_gb < 4.5):
        return "low"
    if cores >= 8 and (ram_gb is None or ram_gb >= 16):
        return "high"
    return "standard"


def get_hardware_profile(preference: str = "auto") -> HardwareProfile:
    cores, ram_gb = detect_hardware()
    name = choose_profile_name(cores, ram_gb) if preference == "auto" else preference
    if name not in _PROFILES:
        raise ValueError(f"Unknown hardware profile: {name}")
    return HardwareProfile(name=name, cpu_cores=cores, ram_gb=ram_gb, **_PROFILES[name])
