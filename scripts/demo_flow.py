#!/usr/bin/env python3
"""End-to-end demo of every SecurePrint module against a RUNNING server.

Usage:
  python scripts/demo_flow.py --admin-password '<admin password from seed_database.py>'
  (or set DEMO_ADMIN_PASSWORD).  Exit code 0 = every step behaved as expected.

Each run uses a uniquely sized model so it never collides with a previous run's design.
"""
import argparse
import io
import os
import random
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.geometry import samples

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        FAILED.append(label)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--admin-password", default=os.environ.get("DEMO_ADMIN_PASSWORD", ""))
    args = parser.parse_args()
    if not args.admin_password:
        print("Provide --admin-password or DEMO_ADMIN_PASSWORD")
        return 2

    http = httpx.Client(base_url=args.base, timeout=60)
    health = http.get("/health").json()
    check("Server healthy", health.get("status") == "healthy", str(health))

    login = http.post("/api/auth/login",
                      json={"username": args.username, "password": args.admin_password})
    if login.status_code != 200:
        check("Login", False, f"HTTP {login.status_code}")
        return 1
    http.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    check("Login", True)
    check("Wrong password rejected",
          http.post("/api/auth/login", json={"username": args.username, "password": "x"},
                    headers={"Authorization": ""}).status_code == 401)

    # --- Module: design security
    dims = tuple(round(random.uniform(20, 90), 2) for _ in range(3))
    triangles = samples.make_box(dims, (8, 4, 2))
    good = samples.write_binary_stl(triangles)
    bad = samples.write_binary_stl(samples.tamper_mesh(triangles, 0.5))
    reg = http.post("/api/designs", files={"file": ("demo.stl", good)}, data={"name": "Demo part"})
    check("Register design (encrypted, fingerprinted)", reg.status_code == 201, reg.text[:80])
    design_id = reg.json().get("id")
    verdict = http.post("/api/designs/verify", files={"file": ("demo.stl", good)}).json()
    check("Identical file verifies AUTHENTIC", verdict.get("verdict") == "AUTHENTIC")
    verdict = http.post("/api/designs/verify", files={"file": ("demo.stl", bad)},
                        data={"design_id": design_id}).json()
    check("Altered file detected as TAMPERED", verdict.get("verdict") == "TAMPERED")

    # --- Module: AI quality control
    from PIL import Image
    buf = io.BytesIO()
    Image.effect_noise((128, 128), 40).save(buf, format="PNG")
    insp = http.post("/api/quality/inspect", files={"file": ("print.png", buf.getvalue())})
    body = insp.json() if insp.status_code == 200 else {}
    check("AI defect inspection returns a result", insp.status_code == 200,
          f"{body.get('defect_type')} ({body.get('confidence')})" if body else insp.text[:80])

    # --- Module: manufacturing security
    safe = http.post("/api/manufacturing/analyze-gcode",
                     files={"file": ("ok.gcode", b"G28\nG1 X10 Y10 F1500\nM104 S200\n")}).json()
    evil = http.post("/api/manufacturing/analyze-gcode",
                     files={"file": ("evil.gcode", b"G28\nM104 S400\nG1 X999 Y999\n")}).json()
    check("Safe G-code passes", safe.get("safe") is True)
    check("Malicious G-code flagged HIGH risk", evil.get("risk") == "HIGH")

    # --- Module: supply chain
    part = http.post("/api/supply-chain/parts",
                     json={"design_id": design_id, "batch": "DEMO", "material": "PLA"})
    check("Create part", part.status_code == 201)
    part_id = part.json().get("id")
    steps = ["DESIGN_APPROVED", "SLICED", "PRINT_STARTED", "QUALITY_INSPECTED",
             "QUALITY_APPROVED", "CERTIFIED", "SHIPPED", "RECEIVED"]
    done = all(http.post(f"/api/supply-chain/parts/{part_id}/events",
                         json={"action": a}).status_code == 201 for a in steps)
    check("Record full provenance workflow", done)
    chain = http.get(f"/api/supply-chain/parts/{part_id}/verify").json()
    check("Provenance chain verifies (signed hash chain)", chain.get("valid") is True)
    code = part.json().get("part_code")
    auth = http.get(f"/api/supply-chain/authenticate/{code}").json()
    check("Part authenticates AUTHENTIC", auth.get("verdict") == "AUTHENTIC")

    # --- Module: audit + compliance
    audit = http.get("/api/audit/verify").json()
    check("Audit log chain intact", audit.get("valid") is True, f"{audit.get('checked')} entries")
    comp = http.post("/api/compliance/run").json()
    check("Compliance checks run", comp.get("total", 0) > 0,
          f"{comp.get('pass_count')} pass / {comp.get('fail_count')} fail / "
          f"{comp.get('unknown_count')} unknown")
    check("No compliance control failing", comp.get("fail_count") == 0)
    dash = http.get("/api/dashboard/summary").json()
    check("Dashboard reflects the new data", dash.get("designs", 0) >= 1 and dash.get("parts", 0) >= 1)

    print()
    if FAILED:
        print(f"{len(FAILED)} step(s) FAILED: {', '.join(FAILED)}")
        return 1
    print("DEMO COMPLETE: every module behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
