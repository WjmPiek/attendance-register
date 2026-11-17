# Requisitions in Attendance

The desktop web sidebar includes **Requisitions** for franchise holders, administrators and explicitly selected staff. Employee and manager accounts have no access by default. Their existing commission upload permission does not grant requisition access. Mobile browsers and native mobile apps do not show this module.

## Branch setup and access

1. Deploy the backend with `python -m alembic upgrade head` (new head: `030_requisitions`), then deploy the frontend.
2. Open Requisitions as the franchise holder or administrator. Administrators choose a holder group first.
3. Under **Staff access**, enable the specific active employees and managers who need the module. Enabled staff can view and use every active linked branch belonging to that holder. The existing signed main-system branch group is authoritative; unrelated holders and external commission-only branches are excluded.
4. Under **Books & monthly setup**, create the first monthly register for each branch, with its card holder and initial opening balance. Download a blank workbook for branch reuse if needed.

Record and source files are stored centrally in PostgreSQL, grouped by holder, branch and month. The source PDF is stored once even when it contains multiple MF files. Receipts and export downloads require authentication and a current grant. No ephemeral Render filesystem storage is used.

## Employee workflow

1. Choose the branch and monthly register.
2. Import the branch's original, unprotected Mortuary Book PDF (maximum 10 MB and 50 pages). The existing mortuary parser extracts MF number, deceased name, ID, collection details and dates. Import is atomic: unreadable pages or a different printed branch reject the batch. Existing MF references are reused; conflicting deceased names require review.
3. Select an imported MF file, requisition date and employee. **Create & enter payments** opens its dedicated form view. The employee identity is taken from the signed-in account.
4. Enter additional deceased/service details and all payment items, explicitly choosing EFT, cash or card for each. The total updates automatically. PDF and Excel forms group items by method.
5. Save drafts as needed. An accidental draft can be discarded; submitted records are immutable. Submit queues the numbered requisition PDF plus an updated monthly Excel workbook to **wjm@martinsdirect.com**. Each additional service application is separately numbered and emailed.
6. Record actual card/cash spending with its exact date, supplier, description, requisition number and original PDF/JPEG/PNG receipt (maximum 10 MB). The holder/administrator records actual card funding and EFT payments with proof. Recording in Attendance does not initiate a bank payment or automatically import bank transactions.

Every transaction sends an updated monthly workbook. Its requisition number links back to the same MF file, including when spending falls in a later month than the original application. Evidence stays available in the register.

## Monthly reconciliation

- **Card balance = opening balance + actual card reimbursements − card purchases.** EFT and cash are separate disclosure columns and do not change the card balance.
- Submission records requested amounts separately; it never credits money that has not yet been loaded onto the card.
- The holder checks the receipts and closes the month. All drafts must be submitted or discarded first. Closed months reject further changes.
- Create the immediately following month. Its opening balance is taken from the previous month's immutable closing balance; an override cannot replace the carry-forward.
- The export starts on **Card Transactions**. K10 contains the brought-forward balance. Rows 11 onward use G for actual reimbursement, H for requisition number, I for card purchases, J for EFT, and K for the running card balance. Cash and receipt filenames have additional columns. **Requisition Forms** contains submitted applications and grouped payment items. The blank export retains an empty reusable form.

The supplied Personal Vault workbook could not be opened. The runtime export follows the written requirements and screenshots; exact sheet-2 fields and styling must be compared with an accessible copy before declaring template parity.

## Email delivery and operations

Uses the existing SMTP configuration documented in `MICROSOFT_365_SMTP_RENDER.md`. No new email credentials or bank connection is introduced. The recipient is fixed server-side to wjm@martinsdirect.com.

Each financial mutation and its email attachment snapshot commit together. A background delivery attempt runs after commit, and the existing 60-second automation checks the durable outbox. Confirmed failures retry after 15 minutes; the holder can also retry pending/failed messages in the page. Missing SMTP configuration is shown in the module.

A committed `sending` marker protects against process interruption after SMTP acceptance. `sending` or `uncertain` items require mailbox review and are never blindly resent. Email state is visible separately from financial submission state; an email failure does not undo a saved application. Sending is only confirmed after SMTP accepts the message, not after mailbox receipt.

Access changes, imports, drafts, submissions, postings and month closure use the existing audit log. Monetary arithmetic uses integer cents. Branch-level PostgreSQL locks serialise month changes and postings; unique request numbers and transaction retry keys protect repeated submissions.

## Validation

Backend workflow tests cover grants, linked-branch scope, cross-holder file isolation, import rejection, exact cents, requested versus funded amounts, card/EFT/cash balance treatment, receipt evidence, duplicate retries, immutable submission, month closure/carry-forward, later-month spending, workbook formulas, formula injection, migration/model parity, SMTP retries and uncertain delivery.

Frontend interaction tests cover the create/save/submit form and restricted finance controls. Build and existing staff/attendance tests are also run. Production PostgreSQL migration, SMTP delivery and exact workbook template comparison require deployment/environment validation; local tests use SQLite and mocked SMTP.
