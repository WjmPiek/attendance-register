# Phase 3 Office Code Deployment

## Included behavior

- Office attendance requires the assigned office's four-digit code.
- The backend checks that the employee or manager is inside the configured
  office radius before accepting sign-in or sign-out.
- Open sessions and sign-in events remain visible before sign-out.
- Session date filters retain open sessions that started before the selected
  date window.
- Attendance exports default to users who have records in the current filters.
- Franchise office management displays the code and prints it on the office PDF.

## Deployment

From the project root:

```powershell
python -m compileall backend\app backend\alembic\versions
python -m pytest backend\tests -q
python scripts\verify_v3.py

cd frontend
npm run build
cd ..

git add .
git commit -m "phase3 require four digit office attendance code"
git push origin main
```

After the backend deployment is live, open the Render backend shell:

```bash
cd /opt/render/project/src/backend
python -m alembic upgrade head
python -m alembic current
```

Expected migration head after the weekly-code/GPS correction:

```text
012_weekly_office_codes (head)
```

## Important production note

Migration 012 forces a new weekly code and records its ISO week. Previously
printed sheets must be replaced. In HR Staff, open **Office Attendance Codes**,
confirm the physical office marker, saved coordinates, preview distance and
radius, then download/print the new one-page portrait A4 code sheet.

Codes rotate on the first list, print, validation or attendance request in each
new ISO week. The old code stops working.

Mobile login now compares usernames and email addresses case-insensitively and
disables phone keyboard auto-capitalization. A `401 Invalid credentials` still
means the password does not match; reset it from the staff member's HR action
menu and test the exact username shown in HR Staff.

## Production verification

1. Assign a manager or employee to an active office.
2. Confirm that office has latitude, longitude, and a radius.
3. Print the new office sheet and note its four-digit code.
4. Inside the radius, verify that the code permits sign-in.
5. Before signing out, verify that Sessions shows an `open` row and Events
   shows the `sign_in` event.
6. Export Sessions and Events and confirm the sign-in appears.
7. Outside the radius, verify that office attendance is rejected.
8. Return inside the radius and sign out; verify the session becomes complete.
