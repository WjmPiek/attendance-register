# Multi-user PDF export and user selector fixes

Implemented:
- Replaced free-text User ID field with a name-based dropdown so the API always receives a numeric user_id.
- Added visible attendance users endpoint: GET /api/attendance/visible-users.
- Added multi-user export panel with checkboxes by user name.
- Single selected user exports one PDF.
- Multiple selected users export a ZIP containing one individual PDF per user.
- Batch export endpoint: GET /api/attendance/export-batch?view=sessions&user_ids=1&user_ids=2.
- Keeps the existing franchise/manager/superuser attendance visibility checks before every PDF is generated.

Notes:
- Restart the backend after replacing files.
- Restart the frontend dev server after replacing files.
- If packages are not installed, run npm install in frontend before npm run dev/build.
