#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Installing Attendance Register Platform for desktop development..."
if [ -d backend ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -r backend/requirements.txt
fi
if [ -d frontend ]; then
  cd frontend
  npm install
  npm run build
  cd ..
fi
echo "Done. Start backend and serve the frontend over HTTPS or localhost, then use the in-app Install App button."
