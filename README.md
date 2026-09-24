# SecurePrint AI — AI-Driven 3D/4D Printing Security Platform (academic MVP)

> Work in progress: **Phase 3 (frontend foundation)** of 10. Frontend, design security, AI quality
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
