# Requested fixes implemented

- Manager attendance/history/export scope now includes only the manager and employees directly assigned to that manager, not other managers or franchise-wide staff.
- Manager dashboard staff visibility now includes only directly assigned employees.
- Leave decisions remain final: only pending applications can be approved/declined, and users cannot decide their own leave.
- Notification "Mark read" permissions now support direct recipients safely; read notifications are removed from Latest and shown under Notification History.
- Mobile sign-in/out now clears signature/QR form state and shows a Done button that returns mobile staff to the home menu.
- ID photo uploads are validated server-side and must be at least 1500x1000 pixels before being stored for ID/business cards.
- Existing website QR generation was verified to normalize the franchise website to an HTTPS URL and use it as the staff-card QR target.

## Validation

- Python backend source compiles successfully with `python -m compileall backend/app`.
- React production build succeeds with `npm install --ignore-scripts && npm run build`.
- A normal `npm ci` could not complete in the isolated build environment because Sharp attempted to download libvips from GitHub; this is a network restriction, not a source build error.

## Larger payroll workflow not included in this patch

The requested automatic overtime/event/commission calculation and month-end payslip generation requires new database tables, payroll rules (rates and tax treatment), approval policy, scheduled jobs, and payslip templates. It should be implemented as a separate reviewed migration to avoid corrupting live payroll data.

## Commission and overtime module
- Added franchise-specific commission structures for Removals, Grave Service, Full Funeral Service, Cremation Service, Church Service and Invoice Commission.
- Invoice commission calculates a configured percentage from a manually entered invoice value before tax.
- Added overtime structures and manual overtime entries using hours x hourly rate x multiplier.
- Added per-employee commission/overtime totals and date filtering.
- Added PDF export for commission and overtime reports.
- Franchise users can configure structures and add/delete entries only for employees in their own franchise.
- Managers can view reports only for employees assigned to them.
- Employees have a Commission & Overtime tab on their own login and can see only their own records.
- Added runtime PostgreSQL schema creation for commission_structures and commission_entries.
