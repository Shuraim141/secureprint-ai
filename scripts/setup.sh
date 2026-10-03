#!/usr/bin/env bash
# One-command setup: virtualenv, dependencies, .env, database + demo users, demo ML models.
# Usage (from repo root):  bash scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements-dev.txt

[ -f .env ] || python scripts/init_env.py
if [ ! -f data/secureprint.db ]; then
  echo "Creating database and demo users (passwords are shown ONCE, save them):"
  python scripts/seed_database.py
else
  echo "Database already exists, keeping it."
fi
[ -f ml/models/defect_detector.joblib ] || python ml/training/train_defect_model.py | tail -3
[ -f ml/models/process_quality.joblib ] || python ml/training/train_process_model.py | tail -3
python scripts/health_check.py
echo
echo "Setup complete. Activate with:  source .venv/bin/activate"
echo "Then run:  bash scripts/check_all.sh   (same checks as CI)"
