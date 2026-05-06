# V18 fixes

- Uses Africa/Johannesburg time for new attendance, leave and notification timestamps.
- Formats frontend dates as South African dd/mm/yyyy where displayed.
- Leave application form now uses dd/mm/yyyy inputs and auto-calculates days requested.
- Leave approval/decline updates the database and writes `decided_by_user_id`, `decided_at`, `updated_at`.
- Leave submission/approval/decline creates notifications linked to the franchise user the employee belongs to.
- SMTP settings now load from backend `.env` via app settings instead of raw OS env only.
- Notification outbox records `sent`, `failed`, or `pending` with `error_message` for troubleshooting.
- No startup migration added.
