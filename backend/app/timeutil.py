"""Time helpers. All timestamps in SecurePrint AI are timezone-aware UTC."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    """Canonical timestamp string used inside hashes (microsecond precision, UTC)."""
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")
