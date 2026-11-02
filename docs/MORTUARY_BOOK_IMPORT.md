# Mortuary Book removal commissions

Franchise holders open **HR Staff → Mortuary Book**. Head Office must select the
franchise first. A selected employee may import when the holder explicitly enables document-import access; only the holder/Head Office can change policies.
Normal central module licence checks still apply.

1. Open **Configure hours and removal rates**. Enter the four franchise default
   fees: driver/assistant, each for business hours and out of hours. Set equal
   driver and assistant rates if both should receive the same fee.
2. Select an employee to save their own six-day weekly business-hour schedule and
   optional rate overrides. Blank employee rates inherit franchise defaults.
   These schedules apply to removal fees, independently of attendance shifts.
3. Defaults are Monday–Friday 08:00–17:00, Saturday 08:00–13:00. End times are
   exclusive. Closed days, Sundays and South African public holidays are out of
   hours. Standard holidays include the Monday after a Sunday holiday; franchise
   defaults can include additional proclaimed public holiday dates.
4. Select original searchable Mortuary Book PDFs, up to 30 files per batch,
   10 MB per file, 50 MB total and 100 records. Each page must have one register.
   Unreadable/scanned/password-protected pages are reported and excluded visibly.
5. Check each Driver In name's matched active employee and Driver/Assistant role.
   A unique exact full-name or first-name match is suggested within the franchise.
   Ambiguous or missing matches require manual selection. Two source names on a
   record cannot be allocated to the same employee. A driver explicitly identified
   by the printed Driver field is suggested as Driver; roles remain editable.
6. Review the staff/role allocations and save the books as waiting evidence. Saving
   a book alone earns no commission, even when its removal rate is configured.
7. Import MF File Receipts, select enabled receipt recipients and review matched
   commissions. Matching branch and MF number, enabled employee categories, valid
   fees and applicable VAT settings are required before approved entries are added.
   See MF_RECEIPT_COMMISSIONS.md for the full paired-document workflow.

## Field mapping

| Printed field | Commission field |
| --- | --- |
| Mortuary Book | Type: removals |
| Date Generated | Service date |
| MF Number | Reference |
| Branch Name | Branch |
| Each allocated Driver In name | One employee entry, quantity 1 |
| Date In and Time In | Business/out-of-hours classification in South African local time |
| Deceased name, ID Number, Collected At, Driver In, Date In, Time In | Notes, with role and fee classification |

Each employee receives their configured fee independently; no automatic splitting.
The printed generation date is deliberately separate from the removal date.

## Integrity and deployment

Run `python -m alembic upgrade head` in `backend` (revision `016_receipt_commissions`).
The migration only adds tables and a nullable branch column; it changes no existing
commission amounts. The Render backend already runs migrations during its build.

Preview source data and fee quotes are signed, expire after one hour, and are bound
to the importing login. Saving rechecks franchise scope, active staff, settings,
amounts and duplicate status. A changed quote must be recalculated. Each batch is
one database transaction; a failure rolls back every entry in that batch.

A unique franchise/employee/branch/MF key prevents repeated payments even when a
PDF is regenerated with a different Date Generated. Existing matching manual entries
are also detected. Concurrent saves use a franchise transaction lock and a database
unique constraint. Imported source allocations, notes and audit history remain
available after saving. Source PDFs are parsed in memory and are not retained.

Tests: install `backend/requirements-dev.txt`, then run `python -m pytest` from
`backend` with a local test DATABASE_URL. Fixtures use synthetic deceased details.
