# Phase 3 Office Code Deployment

## Included behavior

- Office attendance requires the assigned office's four-digit code.
- The backend records every evidence-complete sign-in or sign-out. Attendance
  outside the configured office radius is not blocked; it is marked
  **Not in office GPS range** and remains pending for review.
- Open sessions and sign-in events remain visible before sign-out.
- Session date filters retain open sessions that started before the selected
  date window.
- Attendance exports default to users who have records in the current filters.
- Franchise office management displays the code and prints it on the office PDF.
- A saved GPS marker stays collapsed until **Edit GPS and radius** is selected.
- QR scanning advances directly to the front-camera photo and then signature.
- Manual four-digit code entry appears only when the user cannot scan.
- Manager attendance and leave approvals now live beside each linked employee
  in **My Staff**, together with commission history and notifications.

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
git commit -m "phase3 staff hub and scan first attendance"
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
3. Confirm that the GPS map collapses after save and reopens only with
   **Edit GPS and radius**.
4. Print the new office sheet and confirm the larger logo fits on one A4 page.
5. Inside the radius, scan the QR and confirm the system captures the front
   camera photo before showing signature and sign-in/out.
6. Confirm the manual four-digit field is hidden until **Cannot scan? Enter
   office code** is selected.
7. Before signing out, verify that Sessions shows an `open` row and Events
   shows the `sign_in` event.
8. Export Sessions and Events and confirm the sign-in appears.
9. Outside the radius, verify that sign-in/out succeeds, preserves the
   signature and coordinates, and Events/Sessions shows **Not in office GPS
   range** with a pending approval.
10. Return inside the radius and sign out; verify the session becomes complete
    while retaining the outside-range exception on the session.
11. As a manager, open **My Staff**, select a linked employee, then verify
    attendance approval/rejection, leave approval/decline, commissions and
    employee notifications are visible in that employee's work hub.
12. Log in to the same deployment from a phone using an admin, manager and
    employee account.
