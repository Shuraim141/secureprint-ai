#!/usr/bin/env python3
"""Validate the local installation. Exit code 0 = all required checks passed.

Usage:
  python scripts/health_check.py                      # in-process checks
  python scripts/health_check.py --url http://127.0.0.1:8000/health   # also query a running server
"""
import importlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

REQUIRED_PACKAGES = ["fastapi", "uvicorn", "pydantic", "pydantic_settings", "sqlalchemy",
                     "argon2", "jwt", "cryptography", "multipart"]
failures = 0


def report(ok: bool, name: str, detail: str = "") -> None:
    global failures
    failures += 0 if ok else 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{': ' + detail if detail else ''}")


def main() -> int:
    report(sys.version_info >= (3, 11), "Python >= 3.11", sys.version.split()[0])
    missing = []
    for package in REQUIRED_PACKAGES:
        try:
            importlib.import_module(package)
        except ImportError:
            missing.append(package)
    report(not missing, "Required packages importable",
           "missing: " + ", ".join(missing) if missing else "all present")
    env_ok = (ROOT / ".env").exists()
    report(env_ok, ".env present", "" if env_ok else "run: python scripts/init_env.py")
    if missing or not env_ok:
        print("\nFix the failures above, then re-run.")
        return 1

    from app.config import get_settings
    from app.database import SessionLocal, init_db
    from app.hardware import get_hardware_profile
    from app.services.health import check_health
    from app.services.seed import seed_roles

    settings = get_settings()
    profile = get_hardware_profile(settings.hardware_profile)
    report(True, "Hardware profile", f"{profile.name} ({profile.cpu_cores} cores, "
           f"{profile.ram_gb and round(profile.ram_gb, 1)} GB RAM)")
    init_db()
    with SessionLocal() as db:
        seed_roles(db)
    health = check_health()
    report(health["database"] == "ok", "Database", health["database"])
    report(health["storage"] == "ok", "Storage writable", health["storage"])
    print(f"[INFO] ML service: {health['ml']} (implemented in Phase 5)")

    if "--url" in sys.argv:
        url = sys.argv[sys.argv.index("--url") + 1]
        if not url.startswith(("http://127.0.0.1", "http://localhost")):
            report(False, "Server check", "only localhost URLs are allowed")
        else:
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:  # nosec B310  # localhost-only, scheme checked above
                    body = json.loads(resp.read())
                report(body.get("status") in {"healthy", "degraded"}, "Running server", str(body))
            except OSError as exc:
                report(False, "Running server", str(exc))
    print("\nAll required checks passed." if failures == 0 else f"\n{failures} check(s) failed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
