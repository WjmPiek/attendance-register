# Requisitions in Attendance

The desktop web sidebar includes **Requisitions** for franchise holders, administrators and explicitly selected staff. Employee and manager accounts have no access by default. Their existing commission upload permission does not grant requisition access. Mobile browsers and native mobile apps do not show this module.

## Branch setup and access

1. Deploy the backend with `python -m alembic upgrade head` (new head: `031_requisition_revisions`), then deploy the frontend.
2. Open Requisitions as the franchise holder or administrator. Administrators choose a holder group first.
3. Under **Staff access**, enable the specific active employees and managers who need the module. Enabled staff can view and use every active linked branch belonging to that holder. The existing signed main-system branch group is authoritative; unrelated holders and external commission-only branches are excluded.
4. Under **Books & monthly setup**, create the first monthly register for each branch, with its card holder and initial opening balance. Download a blank workbook for branch reuse if needed.

Record and source files are stored centrally in PostgreSQL, grouped by holder, branch and month. The source PDF is stored once even when it contains multiple MF files. Receipts and export downloads require authentication and a current grant. No ephemeral Render filesystem storage is used.

## Employee workflow

1. Choose the branch and monthly register.
2. Import the branch's original, unprotected Mortuary Book PDF (maximum 10 MB and 50 pages). The existing mortuary parser extracts MF number, deceased name, ID, collection details and dates. Import is atomic: unreadable pages or a different printed branch reject the batch. Existing MF references are reused; conflicting deceased names require review.
3. Select an imported MF file and requisition date. **Create & enter payments** opens its dedicated form view and immediately generates a REQ number linked to the signed-in employee. The employee name and REQ number cannot be overridden by the browser. The same number remains on submission and every later revision.
4. Choose payment items from BI 1663 / DHA 1663, Schedule B, Coffin Type, Cremation Fee, Canvas, Programs, Flowers, Candles, Platters, Grave Labor and Other. Enter coffin type, canvas type (for example A1), program supplier company or Other description manually. Every amount is entered manually, with EFT/cash/card chosen per item. Only positive-amount items appear on the PDF or Excel form and count toward the total. Unpriced and zero-value rows stay editable in the saved form; they do not appear as requested expenses in emailed files.
5. Save drafts as needed; an accidental draft can be discarded. Submit queues the requisition PDF plus an updated monthly Excel workbook to **wjm@martinsdirect.com**. The author or holder can subsequently correct the form using **Save changes & email revision**. Its REQ number stays unchanged; revision 1, revision 2 and later snapshots are retained, with a fresh PDF and updated register emailed after each change. A stale editor must reopen the latest revision. Retrying an unchanged save does not send another email. Each additional service application is separately numbered and emailed.
6. Record actual card/cash spending with its exact date, supplier, description, requisition number and original PDF/JPEG/PNG receipt (maximum 10 MB). The holder/administrator records actual card funding and EFT payments with proof. Recording in Attendance does not initiate a bank payment or automatically import bank transactions.

Every transaction sends an updated monthly workbook. Its requisition number links back to the same MF file, including when spending falls in a later month than the original application. Evidence stays available in the register.

## Monthly reconciliation

- **Card balance = opening balance + actual card reimbursements − card purchases − EFT payments.** This follows the supplied template and the owner’s explicit choice. Cash is disclosed separately and does not change the card balance.
- Submission records requested amounts separately; it never credits money that has not yet been loaded onto the card.
- The holder checks the receipts and closes the month. All drafts must be submitted or discarded first. Closed ledgers reject further financial postings. Request corrections remain possible as versioned revisions and do not change recorded payments or the closed card balance.
- Create the immediately following month. Its opening balance is taken from the previous month's immutable closing balance; an override cannot replace the carry-forward.
- The export opens on **KAART TRANSAKSIES**, using the supplied Northcliff workbook layout and logos. Month/branch/holder stay at the top. Column A is the transaction number; B is date; C is type; D is employee; E is supplier; F is description including MF reference; G is actual card reimbursement; H is requisition number; I is card spending; J is EFT; K is the running balance. Cash and receipt filename are additional disclosure columns L/M.
- K10 holds the opening balance. Every row uses the preceding balance plus funding minus card purchases minus EFTs. This corrects the original template’s incorrect earlier-row references at K59, K69 and K81. G is populated only for actual funding, preventing the old SUMIF logic from treating purchase amounts as reimbursements.
- Each submitted application has its own **Rekwisisie Vorm - N** worksheet, preserving MF file, deceased name and ID, date of death, date of service, service required, expense, description, amount and total. Branch and employee are added in the original blank detail lines. Payment method is shown in brackets. Signature lines remain blank until genuinely signed; submission does not imply approval.
- The supplied layout has seven payment lines and 71 ledger lines. Exports add rows when needed; totals and month-end balances include the extended area. Blank downloads retain three reusable request forms. Updated instructions are included at the end: every submission and posting is emailed, overriding the older template’s monthly-only note.

The unmodified reference workbook is packaged at `backend/app/templates/requisitions.xlsx`. Generated workbooks use its styles and images; no dependency on an employee’s OneDrive path remains.

## Email delivery and operations

Uses the existing SMTP configuration documented in `MICROSOFT_365_SMTP_RENDER.md`. No new email credentials or bank connection is introduced. The recipient is fixed server-side to wjm@martinsdirect.com.

Each financial mutation and its email attachment snapshot commit together. A background delivery attempt runs after commit, and the existing 60-second automation checks the durable outbox. Confirmed failures retry after 15 minutes; the holder can also retry pending/failed messages in the page. Missing SMTP configuration is shown in the module.

A committed `sending` marker protects against process interruption after SMTP acceptance. `sending` or `uncertain` items require mailbox review and are never blindly resent. Email state is visible separately from financial submission state; an email failure does not undo a saved application. Sending is only confirmed after SMTP accepts the message, not after mailbox receipt.

Access changes, imports, drafts, submissions, postings and month closure use the existing audit log. Monetary arithmetic uses integer cents. Branch-level PostgreSQL locks serialise month changes and postings; unique request numbers and transaction retry keys protect repeated submissions.

## Validation

Backend workflow tests cover grants, linked-branch scope, cross-holder file isolation, import rejection, exact cents, requested versus funded amounts, card/EFT/cash balance treatment, receipt evidence, duplicate retries, employee-bound REQ numbers, catalog/manual descriptions, unpriced/zero-value PDF exclusions, authorised submitted revisions and preserved earlier versions, month closure/carry-forward, later-month spending, workbook formulas, formula injection, migration/model parity, SMTP retries and uncertain delivery.

Frontend interaction tests cover the create/save/submit form and restricted finance controls. Build and existing staff/attendance tests are also run. Production PostgreSQL migration and SMTP delivery require deployment/environment validation; local tests use SQLite and mocked SMTP. The supplied template is now integrated, including field mapping, original drawings and corrected financial formulas.

## Manual acceptance check after deployment

PR #63 must be merged and the backend/frontend deployed before the tab is visible at https://attendance.martinssystem.co.za/. The backend migration must reach `031_requisition_revisions`. Use a staging/test branch and synthetic book/receipts first; submission intentionally queues email to the owner.

1. Sign in as holder/admin on desktop web. Open Requisitions, select the linked group/branch, enable one employee under Staff access, and verify an unselected employee has no access. Mobile must show no requisition tab.
2. Create an initial test monthly register with opening balance R500.00. Import the selected branch’s original Mortuary Book PDF. Create a requisition for its MF file and check the template fields, employee, branch and date.
3. Request two card payments of R600.00 and R150.00, one EFT of R2,000.00 and one cash item of R500.00. The request total must be R3,250.00. Check that the REQ number is generated when the form is created. Add Schedule B without an amount and leave a second item at zero. Submit once: the positive request total must be R3,250.00 and the balance must remain R500.00. The unpriced/zero items must be absent from the emailed PDF and Excel form, while remaining in the employee’s editor.
4. As holder/admin, post actual funding of R3,250.00 with proof: balance R3,750.00. Post card receipts R600.00 and R150.00: R3,150.00 then R3,000.00. Post EFT R2,000.00: R1,000.00. Cash R500.00 is disclosed separately, leaving R1,000.00.
5. Download the workbook: KAART TRANSAKSIES opens first, K10 is R500.00, final K is R1,000.00, G/H/I/J line items and request numbers agree, the requisition form totals R3,250.00, and original proof downloads open. Confirm the email arrives at wjm@martinsdirect.com with the PDF and updated Excel attachment; a queued status alone is not proof of receipt.
6. Close the month after checking receipts, then create the next month. Opening balance must be R1,000.00 and the closed ledger must reject new transactions. Switch between Northcliff/Rivonia/Benoni within the linked holder group and confirm records remain under their original branch; an unrelated holder must not see them.

7. Open the submitted form as its employee. Edit a description (or a manually entered coffin/canvas/company detail) without changing the test amounts. Save changes & email revision. Verify the same REQ number, revision 2 on the new PDF, unchanged posted balance, and receipt of a fresh email. The original revision 1 email/PDF remains intact. A different selected employee must be able to view the linked branch form but must not be able to edit someone else’s request.
