# Attendance Register Platform - Fixes Applied

This package keeps the existing project structure and applies targeted production fixes.

## Fixed

- Overview `Failed to fetch` / alerts summary failure:
  - Removed duplicate `LIMIT 20` in `backend/app/api/alerts.py`, which caused the `/api/alerts/summary` SQL query to fail.
- Notifications:
  - Alerts summary now returns notifications correctly after the SQL fix.
  - Frontend API errors now show a clearer backend connectivity/CORS message instead of only `Failed to fetch`.
- Leave visibility on Overview:
  - Existing approved and pending leave lists are preserved and displayed with return dates.
- UI consistency:
  - Added a final CSS consistency pass to keep normal text at 12px while headings and subheadings remain proportional.
  - Improved table/content vertical alignment for cleaner cross-tab display.

## Files changed

- `backend/app/api/alerts.py`
- `frontend/src/api/client.js`
- `frontend/src/styles.css`

## Run notes

Start the backend first on port `8000`, then run the frontend on port `5173`.

If the frontend and backend run on different hosts/ports in production, set:

```bash
VITE_API_BASE_URL=http://YOUR_BACKEND_HOST:8000/api
```

Then rebuild the frontend.
