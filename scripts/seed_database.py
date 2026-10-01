#!/usr/bin/env python3
"""Initialise the database, roles and demo users.

Usage:
  python scripts/seed_database.py               # idempotent seed
  python scripts/seed_database.py --reset --yes # delete the SQLite file first (demo reset)

Passwords: SEED_PASSWORD from .env if set, otherwise random and printed ONCE below.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal, engine, init_db  # noqa: E402
from app.services.seed import seed_demo_users, seed_printers, seed_roles  # noqa: E402


def reset_sqlite(url: str) -> None:
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite") or not parsed.database:
        raise SystemExit("--reset is only supported for SQLite databases")
    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        Path(f"{parsed.database}{suffix}").unlink(missing_ok=True)
    print(f"Removed {parsed.database}")


def main() -> int:
    settings = get_settings()
    if "--reset" in sys.argv:
        if "--yes" not in sys.argv:
            print("Refusing to reset without --yes")
            return 1
        reset_sqlite(settings.database_url)
    fixed = settings.seed_password or None
    if fixed is not None and len(fixed) < 10:
        print("SEED_PASSWORD must be at least 10 characters")
        return 1
    init_db()
    with SessionLocal() as db:
        seed_roles(db)
        seed_printers(db)
        results = seed_demo_users(db, fixed)
    print(f"{'USERNAME':<14}{'ROLE':<20}PASSWORD")
    for row in results:
        if not row["created"]:
            shown = "(already existed, unchanged)"
        else:
            shown = fixed and "(SEED_PASSWORD from .env)" or row["password"]
        print(f"{row['username']:<14}{row['role']:<20}{shown}")
    if any(r["created"] for r in results) and not fixed:
        print("\nRandom passwords are shown only now. Store them; they are not recoverable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
