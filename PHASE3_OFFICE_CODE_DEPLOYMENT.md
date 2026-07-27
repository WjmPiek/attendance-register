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
- Only a manager or franchise user can view and issue an office code.
- The employee attendance page never displays the active code.
- A code works once, is replaced after successful attendance, and expires
  automatically after 20 minutes if unused.
- A saved GPS marker stays collapsed until **Edit GPS and radius** is selected.
- Employees select **I have a code** only after receiving it from their manager
  or franchise user; successful validation advances to photo and signature.
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
git commit -m "phase3 single use 20 minute office codes"
git push origin main
```

After the backend deployment is live, open the Render backend shell:

```bash
cd /opt/render/project/src/backend
python -m alembic upgrade head
python -m alembic current
```

Expected migration head:

```text
013_single_use_office_codes (head)
```

## Important production note

Migration 013 expires every previous reusable/weekly code. Do not leave a
printed attendance code at the office. In **Office Attendance Codes**, the
manager or franchise user selects **Issue new code** when an employee calls.
The issued code is valid for one successful action and no longer than 20
minutes. After use, the manager refreshes the screen or selects **Issue new
code** for the next employee/action.

Mobile login now compares usernames and email addresses case-insensitively and
disables phone keyboard auto-capitalization. A `401 Invalid credentials` still
means the password does not match; reset it from the staff member's HR action
menu and test the exact username shown in HR Staff.

## Production verification

1. Assign a manager or employee to an active office.
2. Confirm that office has latitude, longitude, and a radius.
3. Confirm that the GPS map collapses after save and reopens only with
   **Edit GPS and radius**.
4. As an employee, confirm the active office code is not displayed.
5. As the linked manager or franchise user, open **Office Attendance Codes**
   and select **Issue new code**.
6. Give the code to the employee and confirm code entry stays hidden until
   **I have a code** is selected.
7. Complete attendance and confirm the same code cannot be used a second time.
8. Issue another code, leave it unused for more than 20 minutes, and confirm it
   is rejected and replaced.
9. Before signing out, verify that Sessions shows an `open` row and Events
   shows the `sign_in` event.
10. Export Sessions and Events and confirm the sign-in appears.
11. Outside the radius, verify that sign-in/out succeeds, preserves the
   signature and coordinates, and Events/Sessions shows **Not in office GPS
   range** with a pending approval.
12. Return inside the radius and sign out; verify the session becomes complete
    while retaining the outside-range exception on the session.
13. As a manager, open **My Staff**, select a linked employee, then verify
    attendance approval/rejection, leave approval/decline, commissions and
    employee notifications are visible in that employee's work hub.
14. Log in to the same deployment from a phone using an admin, manager and
    employee account.
