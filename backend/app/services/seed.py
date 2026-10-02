"""Idempotent seeding of roles and demo users (used by lifespan and scripts/seed_database.py)."""
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.logger import write_audit
from app.models.manufacturing import Printer
from app.models.user import Role, User
from app.security.passwords import hash_password
from app.security.rbac import ROLE_DESCRIPTIONS, RoleName

DEMO_PRINTERS = [
    ("PRINTER-01", "Prusa-style FDM Printer 1"),
    ("PRINTER-02", "Prusa-style FDM Printer 2"),
]

DEMO_USERS = [
    ("admin", "ADMIN", "Demo Administrator"),
    ("engineer1", "ENGINEER", "Demo Engineer"),
    ("inspector1", "QUALITY_INSPECTOR", "Demo Quality Inspector"),
    ("supplychain1", "SUPPLY_CHAIN", "Demo Supply-Chain Officer"),
    ("auditor1", "AUDITOR", "Demo Auditor"),
    ("viewer1", "VIEWER", "Demo Viewer"),
]


def seed_roles(db: Session) -> None:
    existing = set(db.execute(select(Role.name)).scalars())
    for role in RoleName:
        if role.value not in existing:
            db.add(Role(name=role.value, description=ROLE_DESCRIPTIONS[role.value]))
    db.commit()


def seed_demo_users(db: Session, fixed_password: str | None = None) -> list[dict]:
    """Create missing demo users. Returns [{username, role, password|None, created}].
    Passwords are random unless a fixed one is supplied; they are shown once and never stored
    in plaintext."""
    results = []
    for username, role_name, full_name in DEMO_USERS:
        if db.execute(select(User).where(User.username == username)).scalar_one_or_none():
            results.append({"username": username, "role": role_name, "password": None,  # nosec B105
                            "created": False})
            continue
        role = db.execute(select(Role).where(Role.name == role_name)).scalar_one()
        password = fixed_password or secrets.token_urlsafe(12)
        db.add(User(username=username, full_name=full_name, role_id=role.id,
                    password_hash=hash_password(password)))
        db.commit()
        write_audit(db, action="SEED_USER_CREATED", user="system", resource=f"user:{username}",
                    details={"role": role_name})
        results.append({"username": username, "role": role_name, "password": password,
                        "created": True})
    return results


def seed_printers(db: Session) -> None:
    """Idempotent: creates the demo printers referenced throughout Module F/G/H/I/K if they
    do not already exist. No physical printer is required -- see app/manufacturing/simulator.py."""
    existing = set(db.execute(select(Printer.printer_code)).scalars())
    for code, name in DEMO_PRINTERS:
        if code not in existing:
            db.add(Printer(printer_code=code, name=name, adapter="simulator", state="idle"))
    db.commit()
