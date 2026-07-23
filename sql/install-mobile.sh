#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "Preparing mobile install build..."
cd frontend
npm install
npm run build
cat <<'MSG'
Mobile build ready in frontend/dist.
Deploy frontend/dist behind HTTPS, then open it on the phone and choose Install/Add to Home Screen.
MSG
