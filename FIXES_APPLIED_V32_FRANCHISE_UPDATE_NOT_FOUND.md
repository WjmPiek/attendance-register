# V32 Franchise Update Not Found Fix

Fixes the Franchise Registration Approvals edit/save error where the UI displayed `Not Found` and no data was saved.

## Changes
- Added robust backend update helper for franchise registration edits.
- Added compatible `PUT`, `PATCH`, and `POST /edit` update endpoints.
- Synces approved registration edits back to the linked `franchise_users` row, including `website`, so staff ID QR codes use the updated franchise website.
- Frontend update call now tries compatible fallback routes if an older backend route returns `Not Found`.

## Apply
1. Replace backend/frontend files with this patch.
2. Restart backend.
3. Restart frontend / hard refresh.
