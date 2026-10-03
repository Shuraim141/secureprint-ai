# Demo guide (about 10 minutes)

## Setup (once)
```bash
bash scripts/setup.sh                 # venv, deps, .env, DB + users (passwords printed ONCE), models
source .venv/bin/activate
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
# second terminal
cd frontend && npm ci && npm run dev  # http://localhost:5173
```

## Automated proof that everything works
```bash
python scripts/demo_flow.py --admin-password '<admin password>'
bash scripts/check_all.sh             # identical to CI
```

## Live walkthrough (log in as `admin`)
1. **Dashboard**: live counts, health badges.
2. **Design Security**: register a model, then verify the same file (AUTHENTIC) and an altered file (TAMPERED with the metric differences).
   Sample files: see "Generate demo models" in the README.
3. **Quality Control**: upload an image, see the defect class, confidence and the model metrics with their honesty disclaimer.
4. **Manufacturing**: start the printer simulator, watch telemetry, upload a malicious G-code and show the HIGH-risk incident.
5. **Supply Chain**: create a part, advance it through all 9 steps, verify the chain, then authenticate it by part code.
6. **Audit Logs**: filter by FAILURE/HIGH, click **Verify chain**.
7. **Compliance**: click **Run checks now**; explain PASS / FAIL / UNKNOWN and the "not a certification" banner.
8. **RBAC**: log in as `viewer1`: sidebar items for Design Security / Compliance are gone and API writes return 403.

## Good questions to be ready for
* *Why not a real blockchain?* A `LedgerBackend` interface exists; the MVP uses a local signed hash chain and documents Fabric as the production path.
* *Is the AI validated?* No: trained on synthetic data, stated everywhere the metrics appear.
* *What would you change for production?* See the upgrade path in `docs/ARCHITECTURE.md`.
