#!/usr/bin/env bash
# One-command start: sets up the Python venv, builds the dashboard if needed and starts the
# ground station on http://localhost:8000
#
#   ./run.sh            production-style (FastAPI serves the built dashboard)
#   ./run.sh --dev      backend + Vite dev server with hot reload on http://localhost:5173
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"

if [ ! -d backend/.venv ]; then
  echo "==> Creating Python virtualenv"
  python3 -m venv backend/.venv
fi
backend/.venv/bin/pip install -q -r backend/requirements.txt

if [ ! -d frontend/node_modules ]; then
  echo "==> Installing dashboard dependencies"
  (cd frontend && npm install --no-audit --no-fund)
fi

if [ ! -f backend/users.txt ] && [ -z "${GS_USERS:-}" ]; then
  echo "!!  No login accounts yet. Create one with:"
  echo "    (cd backend && .venv/bin/python -m groundstation.auth <username> >> users.txt)"
fi

if [ "${1:-}" = "--dev" ]; then
  echo "==> Dev mode: backend :$PORT, dashboard http://localhost:5173"
  (cd backend && .venv/bin/uvicorn groundstation.main:app --host 0.0.0.0 --port "$PORT" --reload) &
  BACK=$!
  trap 'kill $BACK 2>/dev/null' EXIT
  (cd frontend && GS_BACKEND="http://localhost:$PORT" npm run dev)
else
  if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src -newer frontend/dist/index.html -print -quit)" ]; then
    echo "==> Building dashboard"
    (cd frontend && npm run build)
  fi
  echo "==> Ground station running at http://localhost:$PORT (Ctrl+C to stop)"
  cd backend && exec .venv/bin/uvicorn groundstation.main:app --host 0.0.0.0 --port "$PORT"
fi
