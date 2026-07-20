# Fixes Applied V5

## Notification syncing
- Added automatic notifications table migration in `backend/app/api/alerts.py`.
- The backend now adds missing columns automatically: `user_id`, `is_read`, `severity`, `target_tab`, `related_table`, `related_id`, timestamps, and recipient fields.
- Smart notifications are upserted per user/type/day instead of being duplicated on every dashboard refresh.
- Existing notifications are updated with the latest message/severity/link target.
- Notification list now returns link metadata so the frontend can open the correct module.

## Smart alerts
- Overview now groups live operational alerts for:
  - Staff not signed in today
  - Late arrivals
  - Missing sign-outs
  - GPS/area issues
  - Pending leave approvals
  - Approved current/upcoming leave with return dates
- Suggestions include `target_tab` values so they open History, Approvals, or Leave directly.

## Approval logic
- Leave decisions now block self-approval.
- Franchise users can decide leave only inside their franchise scope.
- Managers can decide leave only for their manager scope.
- Attendance approval/rejection now checks visible user scope and prevents re-deciding already approved/rejected events.
- Rejections require a rejection reason.

## Frontend linking
- Overview smart suggestion cards are clickable.
- Notification cards are clickable and navigate to the correct tab.
- Mini alert rows navigate to History, Approvals, or Leave depending on alert type.

## Database note
- No manual DBeaver SQL is required for the notification columns after this version. Start the backend and visit Overview; the backend performs safe `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` migrations automatically.
