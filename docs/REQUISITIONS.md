# Requisitions in Attendance

Deploy through migration `032_requisition_reports`. Desktop staff see a Requisitions home block when selected under Requisitions → Settings. Holders/admins manage access and nominate the monthly report email. Mobile hides this feature. Linked branches share visibility within the authenticated holder group.

## Simple employee flow

1. Requisitions → Requisition → upload the original mortuary-book PDF (up to 10 MB / 50 pages). The printed branch selects its linked branch automatically. Unreadable or unknown-branch books return a plain explanation and leave the batch unchanged.
2. One MF opens its form automatically; multiple MFs require a selection. The server assigns the employee-linked REQ, date, branch, employee, MF and deceased. Recognised client details are prefilled; optional missing details can be entered manually.
3. Choose the requested catalog items, manual types/company/Other description, payment method and amounts. Save drafts as needed. Blank/zero items stay editable but are omitted from the PDF and Excel requisition form.
4. Submit queues a PDF to **wjm@martinsdirect.com** and adds the full total to Card transactions once. A second funding entry is unnecessary and rejected for these requests.
5. Open an existing form to edit it. The original author or holder/admin can save a submitted revision with the same REQ. Earlier versions remain intact; the revised PDF is emailed and only the difference in total changes the register. An unchanged retry does not email or credit again.
6. Card transactions → branch/month → add each payment's REQ, receipt date, supplier, description, Card/EFT/Cash and exact amount. Original PDF/PNG/JPEG proof is required. All three methods deduct from the balance. Payment entries do not send extra emails.

## Shared commission evidence

The same original PDF and parsed MF record are stored in the existing commission evidence system. Duplicate uploads reuse the document. Existing claims reconcile against the evidence using the normal active-staff, branch-specific eligibility, invoice and paid-receipt checks; uploading a book does not itself award commission.

Active employees/managers with enabled commission options can use a **Mortuary book** home block without requisition access. This uploads evidence only. Staff with both permissions use the requisition upload, which already shares the book with commissions. Commission permissions never grant access to financial records.

## Register and monthly email

Balance = opening balance + submitted requisitions − Card payments − EFT payments − Cash payments.

Submission writes an immutable allocation; revisions post signed differences. The first monthly register starts at zero; a later register carries the previous closing balance automatically. Existing opening balances are retained. The legacy holder month API remains available for initial balance/reconciliation. Closed periods keep their original totals; later revisions adjust the next open period. Older manually funded requisitions are not retroactively credited, and legacy separately funded cash retains its original treatment.

The application's existing 60-second scheduler sends a workbook snapshot per branch/month on the **30th at 17:00 Africa/Johannesburg**; February uses its last day. The holder nominates the recipient in Settings, default **wjm@martinsdirect.com**. A durable unique month marker prevents scheduled duplicates after restart. Missed reports are queued when the service resumes. Sending the report does not close the register, so later receipts remain recordable.

The export uses the supplied Northcliff template and logos at `backend/app/templates/requisitions.xlsx`, opening on KAART TRANSAKSIES. K10 is the opening balance; G is submitted allocations/legacy funding; H the REQ; I/J/L Card/EFT/Cash; K running balance; M proof filename. All running formulas refer to the immediately preceding row. Separate Rekwisisie Vorm sheets hold submitted forms. Blank/zero items are excluded. Untrusted text is stored literally in Excel.

Records, originals, receipts, revisions and attachment snapshots are stored in PostgreSQL under holder/branch/month; authenticated downloads enforce current grants. No evidence depends on Render's ephemeral disk. Existing SMTP credentials are reused. Confirmed failures retry after 15 minutes; interrupted/uncertain acceptance is held for review. A queued email is not confirmation of mailbox receipt. Recording a requisition/payment does not execute a bank transfer.

## Check after deployment

1. Refresh desktop web and enable a test employee in Settings. Confirm Requisitions is a home block with no extra sidebar.
2. Upload a linked-branch mortuary PDF. Check branch, REQ, employee, MF and deceased. For a multi-MF book, choose the correct file.
3. Request Flowers R100 and leave another row unpriced. Submit: with zero opening, the register is R100. The emailed PDF should show Flowers only.
4. Add a R25 card receipt: balance R75. EFT and cash receipts also subtract. Compare the downloaded workbook.
5. Edit Flowers to R120 and save changes: same REQ, revised email PDF, balance R95 after the R20 adjustment.
6. A commission-enabled employee/manager without requisition access can upload a Mortuary book and use its MF evidence in commissions, but cannot view card records.
7. Confirm the nominated monthly email in Settings and check the actual mailbox when the report is due on the 30th, 17:00 SA (last day in February).

Automated checks cover branch detection/tenant isolation, shared commission evidence and permissions, automatic draft/month creation, receipts and exact-cent balances, revision adjustments, carry-forward, PDF exclusions, workbook formulas and template expansion, migration parity, monthly due dates/nomination/deduplication and SMTP retry protection. Frontend checks exercise upload-first navigation, multiple MF selection, manual items, editable submissions, receipt controls and denied access.
