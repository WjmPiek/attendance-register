# V31 Staff Load Fix

Fixes HR Staff tab error: `Staff data could not load`.

## Fixed
- Restored missing `_ensure_office_hours_columns()` helper used by `/api/franchise-staff/managers` and `/api/franchise-staff/employees`.
- Added safe/idempotent schema guards for username, website, staff office-hours and profile-photo columns.
- Restored `_valid_hhmm()` used by staff create/edit.
- Restored `_create_user()` used by staff creation.

## Notes
- The SQL guards are safe to run repeatedly because they use `ADD COLUMN IF NOT EXISTS`.
- Restart backend after applying.
