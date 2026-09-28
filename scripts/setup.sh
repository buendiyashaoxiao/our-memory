#!/usr/bin/env bash
# One-time setup on macOS / Linux:  bash scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Creating Python virtual environment (.venv)"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "==> Installing and building the frontend"
(cd frontend && npm ci && npm run build)

.venv/bin/python -m memory_museum doctor
echo
echo "Done. Try the demo:  .venv/bin/python -m memory_museum demo --open"
