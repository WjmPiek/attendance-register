# Grouped branches and matched document commissions

## Linked branches and the monthly document register

Employees stay assigned to their home branch. By default, that branch's commission
permissions and employee fees apply when they work for another linked branch. In
the employee's branch commission card, clear **Use home-branch commission settings**
to set different permissions, fixed fees or invoice percentages for that service
branch. An explicit branch card with no categories enabled blocks all commissions
there. Existing branch-specific settings are retained during upgrade; choose
inheritance explicitly if an old override should use home settings instead.

Commission Claims offers **All linked branches · commission totals** and
**Commission documents · monthly register and activity log**. HR Staff and nominated
uploaders' Upload Proof pages also link to the document register. Each branch has
its own approved subtotal; the holder sees a combined total across all branches.
Employees are never duplicated or transferred to award a linked-branch commission.

The document register uses upload months in South African time and groups the
saved Mortuary Books, invoices and receipts by service branch and MF case. It
displays the invoice amount, all payments to date and outstanding balance; evidence
from earlier upload months still counts towards reconciliation. All three document
types must match branch, MF, deceased identity and invoice/receipt identifiers.
Receipts must balance the invoice exactly: partial and excess payments both block
commission allocation. Reprinted receipts are not extra payments, and the invoice
commission is awarded once for the fully paid invoice rather than per instalment.

Holders and currently nominated uploaders can view originals and extracted fields,
and remove incorrect uploads with a mandatory reason. Removal archives the document
and excludes it from every payment check, manual review and automatic reconciliation.
The original and audit records remain private and retained. Use **Include deleted
uploads** to restore an accidental deletion; a replacement must be removed first.
Cases with active approved commissions are blocked from document removal and require
Head Office financial review. The uploader's access ends when nomination is revoked.

Original PDFs are retained for all three types on new uploads. Older invoices may
already have originals; earlier books/receipts that did not retain files still show
their extracted data and clearly identify that limitation. Uploads, confirmations,
recipient allocations, PDF views/downloads, removals, restorations, blocked deletion
attempts and commission allocations are recorded with actor and time in the activity
log. The register and activity history are paginated.

Migration `024_claim_statements` retains PDF snapshots and changes unsent scheduled
reports to the 26th-to-25th cycle, sent on the 25th at 17:00. Sent, sending and
uncertain reports are preserved.

Migration `022_commission_document_register` adds reversible corrections, an active
document uniqueness index and employee branch override records. It preserves source
records and existing financial amounts. Deploy the backend before the new frontend.

## Holder setup

HR Staff opens a card menu: All Branches & Commissions, MF File Receipt,
Mortuary Book, View Staff, Add New Employee, Office Attendance Codes and My Payslips.
Each opens a separate page with an HR Staff return button. From the branch list,
Commission permissions, Monthly commissions and Employee PDF each open a separate
employee/branch page. Use **Save this commission** to save the branch's permissions;
other branches are preserved. Browser Back and refresh retain the selected page.

Opening Attendance from the main system also fills missing Business Information
from the approved holder's primary franchise: business/trading name, registration,
VAT number, address, website and contact numbers. Existing locally entered values
are preserved (except legacy branch-label placeholders in the business name).
Opening a secondary branch does not copy its VAT or business details over the main
holder's profile. Branch commission VAT settings remain independent.

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
   use the same controls. Home-branch permissions default off; linked branches
   inherit them until overridden. Removals and MF File Receipts
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

## Automatic imports and claims (November 2026)

- Upload Mortuary Book, MF Invoice and all MF File Receipt PDFs in any order.
  Read the detected branch and extracted fields, review excluded pages, then save.
  The printed branch selects the active linked or registered outside branch
  automatically. No employee or commission recipient selection is required.
  Unknown, ambiguous and inactive branches are excluded with correction notices.
- Evidence is grouped by holder, normalised service branch and MF File number.
  A matching MF number at another branch cannot satisfy a claim.
- A manager or employee logs in and enters the MF File number, service branch,
  deceased name and surname, actual service date and enabled commission item.
  The login determines the claimant; staff cannot submit for someone else.
  Holders retain their existing ability to submit a claim for a selected person.
- Only enabled categories and configured service-branch fees are available. One
  claim covers one service item for one person and MF case. Rate overrides,
  multiplied quantities and repeated claims cannot increase the award.
- Removal claims match the claimant uniquely to printed Driver In staff and the
  printed Driver role. Their business hours and Date In/Time In determine the
  business-hours, after-hours or Sunday/public-holiday fixed fee. Unmatched or
  ambiguous staff identities remain blocked.
- Church, grave, full funeral, cremation, joinings and overtime items use configured
  fixed fees. A claim declares who performed these services: the three documents
  verify the case/payment but do not independently prove who performed a service
  when that person's name is absent from the documents.
- MF File Receipt commissions are claimed against the MF case and calculated once
  from the invoice, not once per instalment. Use the configured percentage and the
  invoice commission base resolved against the service branch's VAT record.
  Registered branches use the VAT-exclusive base; confirmed non-VAT branches use
  the full invoice amount. Values round to cents, half-up.
- All three document types must agree on branch, MF number and deceased identity.
  Receipt invoice numbers must match the invoice; conflicting supplied ID numbers
  block the claim. Distinct receipt payments must balance the invoice exactly.
  Partial payments, overpayments and duplicate receipts cannot qualify an award.
- Claims awaiting documents remain red with a reason and an estimate where the
  evidence permits calculation. Missing invoice/removal evidence shows that the
  amount is awaiting checks, rather than presenting a zero as a confirmed fee.
- The background reconciler rechecks pending claims every minute and after uploads.
  Verified, fully paid eligible claims approve automatically. Staff pages refresh
  every 20 seconds. Disabled categories and missing rates never bypass checks.
- Service for Other Branch is an automatic additional fee when the service branch
  is outside the holder's linked group and the person's surcharge is enabled.
  It is added once per person and invoice, even for multiple service categories.
- Existing approved awards and historical document allocations are retained, with
  duplicate checks preventing a new claim from earning the same item again.

## Monthly statements and automatic delivery

- The default cycle is 26th of the previous month through 25th of the report month.
  The in-app scheduler emails the PDF at 17:00 South African time on the 25th,
  without a person pressing Send or saving recipient settings first.
- Recipients are always wjm@martinsdirect.com and finance@martinsdirect.com.
  Business > Commissions shows the schedule, email connection status, delivery
  history and PDF downloads. A holder may adjust an unsent month's dates when
  needed; subsequent months use the default schedule.
- Each holder-group statement lists approved amounts per service branch, person
  and category, branch subtotals, a full approved total and MF claim details.
  A separate pending section is explicitly NOT APPROVED FOR PAYMENT and excluded
  from approved totals. The application does not run payroll or transfer money.
- Approved entries are reserved to one report only. Approvals after the report
  closes carry into the next statement as earlier-period adjustments.
- The exact PDF sent is retained privately with the report and can be downloaded
  by an authorised holder. Historical emails without a PDF say it is unavailable;
  the system does not recreate a historical delivered statement from current data.
- Known delivery failures retry after an hour. An interrupted/uncertain SMTP delivery
  is held for checking rather than automatically sending a potentially duplicate
  payment statement. Delivery errors remain visible in the history.
- The SMTP connection must be configured on the backend. The scheduler starts with
  the application, checks every minute, and catches up due unsent reports after a
  restart. No browser session needs to remain open.

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

Uploads are parsed in memory; source fields and original PDFs are saved privately.
Older imports without saved originals retain extracted details. Signed
previews/quotes expire in one hour and are login-bound.
Changed rates, eligibility, documents or duplicate status require recalculation.
Saving awards is atomic and serialised per holder, with unique database indexes.

Validation includes nonmatching clients, both import orders, per-branch VAT, the
three-branch/one-VAT-vendor case, cross-branch staff, disabled categories, delegation,
20-case batches, duplicates, changed quotes, rollback and filtered PDFs.

