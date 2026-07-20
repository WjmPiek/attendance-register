# Fixes applied v4

## Overview notification linking
- Overview smart notification rows are now clickable.
- Not signed in today opens History.
- Late arrivals, missing sign-outs, and GPS/area issues open Approvals.
- Upcoming/current leave and pending leave approvals open Leave.
- Dashboard tab state and URL query string now update through the existing `openTab()` function.

## CORS/local development hardening
- Backend CORS now allows localhost, 127.0.0.1, and local 192.168.x.x Vite origins.
- Added `allow_origin_regex` for LAN testing.
- Kept backend browser URL guidance: use `localhost:8000` or `127.0.0.1:8000`, not `0.0.0.0`.

## Notes
- The favicon 404 in the browser is harmless and does not affect the app.
- After extracting this ZIP, restart both backend and frontend.
