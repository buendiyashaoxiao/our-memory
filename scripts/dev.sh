#!/usr/bin/env bash
# Development mode: API server + Vite dev server with hot reload.
#   bash scripts/dev.sh            (demo data)
#   bash scripts/dev.sh data       (your private data)
set -euo pipefail
cd "$(dirname "$0")/.."
DATA_DIR="${1:-data/demo}"

if [ "$DATA_DIR" = "data/demo" ] && [ ! -f data/demo/museum.db ]; then
  .venv/bin/python -m memory_museum demo --no-serve
fi
.venv/bin/python -m memory_museum serve --data-dir "$DATA_DIR" &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT
echo "Open http://127.0.0.1:5173/"
(cd frontend && npm run dev)
