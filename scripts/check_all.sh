#!/usr/bin/env bash
# Runs exactly what GitHub Actions runs, locally. Stops at the first failure.
# Usage (from repo root):  bash scripts/check_all.sh
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then echo "No .venv found. Run: bash scripts/setup.sh"; exit 1; fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "== Backend =="
(cd backend && ruff check . && bandit -q -r app && pip-audit -r requirements.txt && python -m pytest -q)
echo "== Frontend =="
(cd frontend && npm ci --silent && npm test && npm run build && npm audit)
echo
echo "ALL CHECKS PASSED"
