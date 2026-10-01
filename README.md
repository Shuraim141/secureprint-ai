# SecurePrint AI — AI-Driven 3D/4D Printing Security Platform (academic MVP)

> Work in progress: **Phase 8 (DevSecOps)** of 10. Frontend, design security, AI quality
> control, supply chain, manufacturing security, DevSecOps and compliance follow in later phases.

## Quick start (Linux / Kali)

```bash
cd secureprint-ai
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements-dev.txt

python scripts/init_env.py            # creates .env with generated JWT_SECRET / MASTER_KEY
python scripts/seed_database.py       # creates DB, roles, demo users (passwords printed ONCE)
python scripts/health_check.py        # validates the installation

cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
# Swagger UI: http://127.0.0.1:8000/docs   Health: http://127.0.0.1:8000/health
```

Windows (PowerShell): `py -3.11 -m venv .venv; .venv\Scripts\Activate.ps1`, then the same
`pip` / `python scripts/...` commands.

## Run the tests

```bash
cd backend
python -m pytest -v
```

## Freeze exact versions (after a successful install)

```bash
pip freeze | grep -iE "^(fastapi|uvicorn|pydantic|pydantic-settings|sqlalchemy|argon2-cffi|pyjwt|cryptography|python-multipart|starlette)==" > requirements.lock.txt
```

## Run the frontend (Phase 3)

Terminal 1 (backend, from `backend/`): `uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log`

Terminal 2:

```bash
cd frontend
npm install
npm test            # Vitest
npm run build       # production build
npm audit           # dependency vulnerabilities
npm run dev         # http://localhost:5173  (Vite proxies /api and /health to port 8000)
```

Log in with a user printed by `scripts/seed_database.py`.

## Phase 4: 3D/4D design security

New backend modules: `app/geometry` (STL/OBJ/3MF parsers, geometry analysis, geometric
fingerprint, fragile watermark), `app/security/crypto.py` (AES-256-GCM envelope encryption),
`app/services/designs.py` (registration, verification, 4D metadata), `app/api/designs.py`.

Generate demo models to try the workflow by hand:

```bash
cd backend
python -c "
import sys; sys.path.insert(0,'.')
from app.geometry import samples
open('/tmp/bracket.stl','wb').write(samples.write_binary_stl(samples.make_box((80,40,12),(10,5,2))))
tri = samples.make_box((80,40,12),(10,5,2))
open('/tmp/bracket_tampered.stl','wb').write(samples.write_binary_stl(samples.tamper_mesh(tri, 0.5)))
"
```

Then, with the backend and frontend both running, open **Design Security** in the sidebar:
1. Register `/tmp/bracket.stl`. Watch the real analysis, fingerprints and encryption status appear.
2. Verify `/tmp/bracket.stl` against it → AUTHENTIC.
3. Verify `/tmp/bracket_tampered.stl` against it → TAMPERED, with the exact metric differences.
4. Add a 4D profile, then verify it → INTACT. Edit `data/secureprint.db` directly (see the
   backend test `test_4d_profile_lifecycle_and_tamper_detection` for the exact SQL) and verify
   again → TAMPERED.

Run its tests: `cd backend && python -m pytest tests/test_geometry.py tests/test_designs.py -v`

## Phase 5: AI quality control

Classical CV (OpenCV) + Random Forest, per the Phase 1 architecture decision — no TensorFlow
by default (see `ml/README.md` for why, and the production substitution point).

**Train the models first** (this does NOT happen automatically at startup):

```bash
python ml/training/train_defect_model.py
python ml/training/train_process_model.py
```

Both print real dataset sizes and evaluation metrics and save `.joblib` files under `ml/models/`
(git-ignored — you must train locally). Until both files exist, `/health` honestly reports
`"ml": "not_configured"`, and `/api/quality/inspect` and `/predict` return 503 with a message
telling you which script to run.

Then, with both servers running, open **Quality Control** in the sidebar (as `inspector1` or
`admin`):
1. Upload any image (a synthetic sample from `ml/training`'s dataset generator works, or any
   photo) → see the predicted class, confidence, per-class probabilities, and the actual
   preprocessed/edge/contour images computed by OpenCV.
2. Try **Predictive quality analytics** → click "Load NORMAL" then "Load SUSPICIOUS" (the exact
   values from this project's specification) → compare predicted quality, risk level and
   anomaly score.
3. Inspection history shows past results from the database.

Generate a few known-class sample images to test with:
```bash
cd backend
python -c "
import sys; sys.path.insert(0,'.')
from app.ml.quality_dataset import generate_image
for label in ['NORMAL','WARPING','STRINGING','LAYER_SHIFT','CLOGGING']:
    open(f'/tmp/{label}.png','wb').write(generate_image(label, seed=1))
"
```

Run its tests: `cd backend && python -m pytest tests/test_quality_ml.py tests/test_quality.py -v`

**Honesty note:** the synthetic demo dataset has strong, clean, procedurally-generated visual
signatures per class, so the defect classifier scores very high on it. That reflects the
dataset, not real-photo performance — every metrics display carries the required disclaimer:
"Metrics are based on the supplied demonstration/synthetic dataset and do not represent
industrial validation." See `ml/README.md` for the full explanation and how to point training
at real labelled photos instead.

## Phase 6: supply chain and part authentication

**Provenance ledger (MVP):** a local, Ed25519-signed, hash-chained event log
(`backend/app/blockchain/ledger.py`). This is *not* Hyperledger Fabric: Fabric needs peers, an
orderer, a CA and chaincode, which is impractical on a student laptop. The ledger implements a
`LedgerBackend` interface so a Fabric adapter can replace it later without touching the service
layer or API. Fabric is the documented production target, not something deployed here.

Each part follows a fixed, enforced workflow:
`DESIGN_CREATED -> DESIGN_APPROVED -> SLICED -> PRINT_STARTED -> QUALITY_INSPECTED ->
QUALITY_APPROVED -> CERTIFIED -> SHIPPED -> RECEIVED`. Each event stores its hash, the previous
event's hash and an Ed25519 signature. The signing key is derived from `MASTER_KEY`, so no
keypair file is stored.

Try it (log in as `engineer1` or `supplychain1`, open **Supply Chain**):
1. Create a part from a registered design.
2. Click **Advance** until RECEIVED, then **Verify chain** -> intact.
3. Authenticate the part code -> AUTHENTIC.
4. Tamper with an earlier event directly in the database:
   `sqlite3 data/secureprint.db "UPDATE supply_chain_events SET actor='attacker' WHERE sequence=2 AND chain_id='PART-000001';"`
5. **Verify chain** / **Authenticate** again -> INTEGRITY FAILURE / TAMPERED at event #2.
   Restore with `SET actor='engineer1'` (use the original actor name).

Known limit: deleting the *last* events of a chain cannot be detected from the chain alone.
Production: anchor each chain head externally (WORM storage or Fabric).

Tests: `cd backend && python -m pytest tests/test_supply_chain_ledger.py tests/test_supply_chain.py -v`

## Phase 7: manufacturing security

**Printer simulator (Module F):** we simulate telemetry in-process because OctoPrint/Klipper
need a physical printer or controller board, neither available to a student. The simulator
implements the same start/pause/stop shape a future OctoPrint/Klipper adapter would, so the
rest of the app would not change. Four scenarios: `NORMAL`, `OVERHEAT`, `SPEED_SPIKE`,
`PARAMETER_TAMPERING`.

**Hybrid anomaly detection (Module G):** hard safety thresholds first (same ranges as
Module A3 and the G-code analyzer), then the trained Isolation Forest for subtler statistical
anomalies if every threshold passes.

**G-code analysis (Module H):** a real line-by-line parser (`backend/app/manufacturing/gcode.py`),
not a filename check. Four sample files under `manufacturing/gcode/`: `safe.gcode`,
`malicious_temperature.gcode`, `malicious_speed.gcode`, `suspicious_command.gcode`.

**Automated incident response (Module I):** Telemetry -> Detection -> Security Event ->
Incident -> Simulated Printer Pause -> Audit Log, with a real database record at every step.

**MES (Module K):** `MESAdapter` interface + `LocalMESSimulator`, because no real industrial
MES is available. Documented production migration: `RealMESAdapter` against the site's actual
MES, with no change to `services/manufacturing.py`.

Try it (log in as `engineer1`, open **Manufacturing Security**):
1. Start `PRINTER-01` on `NORMAL` -> watch live telemetry, completes with no incident.
2. Start it on `OVERHEAT` -> within a few seconds, the printer pauses itself, an incident
   appears below, and a HIGH-severity security event is in the audit log.
3. Upload `manufacturing/gcode/malicious_temperature.gcode` -> SECURITY WARNING, with the exact
   line and the excessive-temperature finding.

Run its tests: `cd backend && python -m pytest tests/test_gcode.py tests/test_manufacturing_simulator.py tests/test_manufacturing.py -v`

## Phase 8: DevSecOps

GitHub Actions (`.github/workflows/ci.yml`) runs the exact same commands used by hand
throughout development, on every push/PR to `main`:

- **Backend job:** `ruff check .`, `bandit -q -r app`, `pip-audit -r requirements.txt`,
  `python -m pytest -v`
- **Frontend job:** `npm ci`, `npm test`, `npm run build`, `npm audit`

No .env file is needed in CI: `tests/conftest.py` sets `JWT_SECRET`/`MASTER_KEY`/`DATABASE_URL`
directly in the environment before the app is imported, exactly as it does for local test runs.
Nothing in this workflow is decorative — a failing step fails the whole run, the same as
running the command locally.

To see it run: push this repository to GitHub (or open a pull request) and check the
**Actions** tab. It can also be triggered manually from there (`workflow_dispatch`).

## Try the API from Swagger

1. `POST /api/auth/login` with a seeded user, copy `access_token`.
2. Click **Authorize** (top right), paste the token, then call `GET /api/auth/me`, `GET /api/audit/logs`, `GET /api/audit/verify`.

## Status honesty

Implemented and tested (Phase 2): see `docs`-style summary in the phase report. Production
technologies (PostgreSQL, Hyperledger Fabric, OctoPrint/Klipper, enterprise IAM, KMS, S3) are
documented upgrade paths, not deployed.

*Academic disclaimer:* This project is an academic MVP demonstrating security, quality assurance,
provenance, and AI concepts for additive manufacturing. It is not intended to provide formal
aerospace, medical, defense, or regulatory certification. Production deployment would require
validated hardware, qualified manufacturing processes, certified models, formal QMS procedures,
security assessment, regulatory approval, and integration with enterprise manufacturing systems.
