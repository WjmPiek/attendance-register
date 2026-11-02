# Grouped branches and matched document commissions

## Holder setup

1. Open Attendance from the main Martins system after deployment. The signed
   handoff now includes the selected holder principal's assigned franchise group,
   with stable main-system branch IDs and recorded VAT numbers. It does not grant
   access to another principal's branches or change the main system's active-branch
   permissions. Reopen Attendance from the main system after changing group links.
2. **HR Staff → View Staff** lists staff by home branch. The branch selector and
   the main system's selected access profile both select this view. Choosing a
   linked profile uses the uniquely approved main holder's Attendance access;
   it does not add Head Office privileges. Existing staff retain their original branch;
   use **View Staff → Edit** to correct their home branch where needed. No accounts
   are merged by matching an email, employee name or branch name.
3. In **Add/Edit Staff**, choose the home branch and use the separate card for each
   linked branch to tick its permitted commission categories. Employees and managers
   use the same controls. New permissions default off. Removals and MF File Receipts
   are separate opt-ins, checked against the document's branch. Each branch card has
   an optional employee receipt percentage overriding employee/branch/holder defaults.
   **All Branches & Commissions** includes people who work at or may earn at each
   branch, and also lets the holder edit that branch's permissions independently.
4. Optionally tick **Allow this employee to import commission documents…**. This
   permits allocation across this holder's active branches, but does not grant
   general access to other employees' HR records, rate settings or group reports.
5. Configure removal business hours and driver/assistant fees in Mortuary Book.
6. In **MF File Receipt**, confirm holder default VAT status and percentage. Select
   a branch to override its VAT status/rate/default percentage. A branch with a
   conflicting recorded VAT number stays unconfirmed until explicitly configured.
   A saved VAT setting is a holder confirmation, not verification against SARS.

## Import and earning rules

- Mortuary Books are saved as waiting evidence; they do not directly award money.
- Import original searchable MF File Receipt PDFs and select the receipt recipients
  from employees whose receipt category is enabled for the printed branch. The list includes home branches
  and searches the entire holder group. A receipt may have no recipients if it is
  only needed to qualify removal commissions.
- Printed franchise names must resolve to an active branch in that holder group.
  Common Martins branding and a trailing `(F)`/`(C)` marker are normalised. Ambiguous
  printed branch names are blocked, rather than guessed.
- A book and receipt must have the same normalised MF number **and document branch**.
  A literal `MF` prefix is ignored. Different MF numbers remain unmatched. When both
  records include an ID number, a conflicting deceased ID blocks the case as well.
- Saving either file can happen first. Use **Review matched commissions for recent
  documents** after adding the missing file, enabling categories or configuring fees.
- The review lists ready, blocked and already-recorded items. Confirming the ready
  entries adds approved commission records to the normal employee Work Hub history.
  Every staff/category allocation is checked again on save.
- Removal recipients come from the saved Driver In allocations; each receives one
  configured fee. Receipt recipients come from the selected, enabled employee list.
- Receipt commission uses **Amount Received**, not balance due plus invoice total.
  For a VAT-registered document branch: `base = amount received / (1 + VAT rate/100)`.
  For a non-registered branch: `base = amount received`. Commission is the rounded
  base times the configured percentage. Values round to cents using half-up.
- The document branch determines VAT even when the employee's home branch differs.
  Each branch can therefore calculate independently when one is registered and
  two others are not. Confirming one branch never silently confirms another with a
  different recorded VAT number.
- Each receipt number pays a given employee once. Multiple real payment receipts
  can earn separate receipt commission for the same MF case; the removal is paid
  only once. Reprinted or repeated PDFs cannot pay a second commission. Conflicting
  details on a previously used receipt number require separate correction/review.
- Disabled categories, missing files, missing fees and unconfirmed VAT settings do
  not earn commission. Manual entry/review endpoints cannot bypass these rules.

## Statements and printing

Employee Work Hubs and commission pages show a monthly category statement with
entry details, deceased name/ID, source MF/receipt, commissionable amount, rate,
category subtotals and monthly total. Only approved entries contribute.

The holder can download PDFs for all branches, one earning branch, or one employee.
Branch statements include only commissions earned for that branch, even when the
employee's home branch differs. Reports retain both branches separately.
New awards snapshot the employee branch and VAT calculation, so later settings or
branch transfers do not rewrite already approved financial records.

Service date remains Date Generated for removal books and the printed receipt date
for receipt commission. They may therefore fall in different monthly statements.

## Deployment and retention

The additive `016_receipt_commissions` migration creates branch assignments, opt-ins,
receipt settings and source-document evidence, and nullable source links on existing
commission entries. Existing approved amounts remain unchanged; historical removal
imports retain their source linkage and cannot be paid again.

Migration `017_commission_branch_scope` adds branch-specific opt-ins and earning
branches. Existing category permissions are initially assigned only to the staff
member's current home branch; the holder must explicitly enable other branches.
Existing entries use their recorded source branch where identifiable, otherwise
their home branch. Approved amounts are preserved.

The main system also needs the updated signed Attendance handoff. Deploy Attendance
first, then the main-system launch change. Existing native Attendance accounts stay
in their original holder scope. Distinct legacy holder accounts are not merged.

Uploads are parsed in memory, source fields are saved privately, and source PDFs
are not retained. Signed previews/quotes expire in one hour and are login-bound.
Changed rates, eligibility, documents or duplicate status require recalculation.
Saving awards is atomic and serialised per holder, with unique database indexes.

Validation includes nonmatching clients, both import orders, per-branch VAT, the
three-branch/one-VAT-vendor case, cross-branch staff, disabled categories, delegation,
20-case batches, duplicates, changed quotes, rollback and filtered PDFs.
