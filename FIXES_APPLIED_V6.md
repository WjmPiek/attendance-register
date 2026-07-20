# Attendance Register Platform - Fixed v6

This package continues from the working project state and keeps the existing Flask/FastAPI backend + Vite frontend structure. It does not rebuild the app.

## 1. alerts.py cleanup
- Added safe notification table migration on startup/use.
- Added missing notification columns automatically:
  - user_id
  - is_read
  - severity
  - target_tab
  - related_table
  - related_id
  - updated_at
- Reworked notification upsert logic so daily system notifications update instead of duplicating.
- Added target tabs for Overview actions:
  - not signed in -> History
  - late arrivals -> Approvals
  - missing sign-out -> Approvals
  - GPS issues -> Approvals
  - pending/approved leave -> Leave
- Smart alerts now return metrics, lists, suggestions and clickable notification metadata.

## 2. Notification syncing
- Overview summary now generates/updates notifications consistently.
- `/api/alerts/notifications` returns user-specific and global notifications.
- `/api/alerts/notifications/{id}/read` marks notifications read and updates status.
- Notifications include severity and target tab for the frontend.

## 3. Approval logic cleanup
- Attendance approval now blocks self-approval.
- Approval lists respect manager/franchise/superuser scope.
- Global filters are passed into approval requests.

## 4. Global filters
- Dashboard now has a shared filter bar for Franchise, User, Status, From and To.
- Filters are passed to Overview, History, Approvals, Leave and Payroll pages.
- Page-level filters still work, with global filters taking precedence where applicable.

## 5. Payroll import auto-matching
- Added payroll import tables and safe migrations.
- Added `/api/payroll/import-document` endpoint.
- Supports CSV and Excel uploads.
- Auto-matches employees by:
  - user_id / employee_id
  - email
  - full name
- Updates payroll settings dynamically while preserving existing values when uploaded fields are blank.
- Stores import audit rows with matched/unmatched status and match method.
- Frontend Payroll tab now includes an import panel and import history.

## Run commands
Backend:
```powershell
cd "D:\ATTENDANCE REGISTAR\attendance_register\backend"
uvicorn app.main:app --reload
```

Frontend:
```powershell
cd "D:\ATTENDANCE REGISTAR\attendance_register\frontend"
npm run dev
```

Open:
```text
http://localhost:5173
```
