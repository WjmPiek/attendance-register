"""Money is integer cents; only posted card funding and card spending affect balance."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
import json
from xml.sax.saxutils import escape
from fastapi import HTTPException
from sqlalchemy import select, text
from app.api.deps import get_user_role_names
from app.models.requisitions import (
    RequisitionGrant,
    RequisitionMonth,
    Requisition,
    RequisitionBook,
    RequisitionTransaction,
    RequisitionEmail,
)

RECIPIENT = "wjm@martinsdirect.com"


def scope(db, user, requested=None, manage=False):
    roles = get_user_role_names(db, user.id)
    admin = bool(roles & {"SuperUser", "FranchiseUser"})
    if "SuperUser" in roles:
        fid = requested
    else:
        table = (
            "franchise_users"
            if "FranchiseUser" in roles
            else (
                "manager_users"
                if "ManagerUser" in roles
                else "employee_users" if "EmployeeUser" in roles else None
            )
        )
        if not table:
            raise HTTPException(403, "Requisitions access is not enabled.")
        column = "id" if table == "franchise_users" else "franchise_user_id"
        fid = db.execute(
            text(f"SELECT {column} FROM {table} WHERE user_id=:uid AND is_active=TRUE"),
            {"uid": user.id},
        ).scalar()
        if requested not in (None, fid):
            raise HTTPException(403, "This holder group is outside your access.")
    if not fid:
        raise HTTPException(
            400 if admin else 403, "Select an active franchise holder group."
        )
    if not db.execute(
        text("SELECT id FROM franchise_users WHERE id=:fid AND is_active=TRUE"),
        {"fid": fid},
    ).scalar():
        raise HTTPException(403, "Holder group is inactive or unavailable.")
    if manage and not admin:
        raise HTTPException(
            403,
            "Only the franchise holder or administrator can manage access, funding and month closure.",
        )
    if not admin and not db.scalar(
        select(RequisitionGrant.id).where(
            RequisitionGrant.franchise_user_id == fid,
            RequisitionGrant.user_id == user.id,
        )
    ):
        raise HTTPException(
            403, "Requisitions access is not enabled for this staff member."
        )
    return fid, admin


def branch(db, fid, bid):
    from app.services.attendance_branches import branches

    item = next((b for b in branches(db, fid) if b["id"] == bid), None)
    if not item:
        raise HTTPException(
            403, "Branch is inactive or outside the linked holder group."
        )
    return item


def lock_branch(db, bid):
    # The same branch lock serialises month rollover, submission and all postings.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(15030,:bid)"), {"bid": bid})


def month_row(db, fid, mid, writable=False):
    item = db.get(RequisitionMonth, mid)
    if not item or item.franchise_user_id != fid:
        raise HTTPException(404, "Monthly register not found.")
    branch(db, fid, item.branch_id)
    if writable:
        lock_branch(db, item.branch_id)
        db.refresh(item)
        if item.status != "open":
            raise HTTPException(
                409, "This month is closed. Use the new monthly register."
            )
    return item


def request_row(db, fid, rid, writable=False):
    req = db.get(Requisition, rid)
    if not req:
        raise HTTPException(404, "Requisition not found.")
    month = month_row(db, fid, req.month_id, writable)
    if writable:
        db.refresh(req)
    return req, month


def cents(value):
    return int(Decimal(str(value)) * 100)


def balance(db, month):
    rows = db.scalars(
        select(RequisitionTransaction).where(
            RequisitionTransaction.month_id == month.id
        )
    ).all()
    return month.opening_cents + sum(
        (
            t.amount_cents
            if t.kind == "funding"
            else -t.amount_cents if t.kind == "card" else 0
        )
        for t in rows
    )


def req_data(db, req):
    book = db.get(RequisitionBook, req.book_id)
    return {
        "id": req.id,
        "month_id": req.month_id,
        "branch_id": db.get(RequisitionMonth, req.month_id).branch_id,
        "employee_id": req.employee_id,
        "book_id": req.book_id,
        "number": req.number,
        "employee_name": req.employee_name,
        "request_date": req.request_date.isoformat(),
        "status": req.status,
        "reference": book.reference,
        "deceased": book.deceased,
        "details": json.loads(req.details),
        "lines": json.loads(req.lines),
        "total_cents": req.total_cents,
    }


def workbook_bytes(db, month, branch_name, blank=False):
    # This is a runtime app export, using the application's existing Excel dependency.
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Card Transactions"
    for row, label, value in [
        (2, "MONTH", month.month),
        (3, "BRANCH", branch_name),
        (4, "HOLDER", month.holder),
    ]:
        ws.cell(row, 1, label)
        ws.cell(row, 3, value)
    headers = [
        "Date",
        "Transaction type",
        "Transaction by",
        "Supplier",
        "MF file",
        "Service/Product Description",
        "Card Reimbursement",
        "Rek. No",
        "Card Transaction",
        "EFT's",
        "Card Balance",
        "Cash",
        "Receipt",
    ]
    for col, value in enumerate(headers, 1):
        ws.cell(9, col, value)
    ws["B10"] = "Brought Forward Balance"
    ws["F10"] = "Brought forward from last month"
    ws["K10"] = month.opening_cents / 100 if not blank else 0
    transactions = (
        []
        if blank
        else db.scalars(
            select(RequisitionTransaction)
            .where(RequisitionTransaction.month_id == month.id)
            .order_by(
                RequisitionTransaction.transaction_date, RequisitionTransaction.id
            )
        ).all()
    )
    for row, t in enumerate(transactions, 11):
        req = db.get(Requisition, t.requisition_id)
        book = db.get(RequisitionBook, req.book_id)
        values = [
            t.transaction_date,
            t.kind,
            t.actor_name,
            t.supplier,
            book.reference,
            t.description,
            t.amount_cents / 100 if t.kind == "funding" else 0,
            req.number,
            t.amount_cents / 100 if t.kind == "card" else 0,
            t.amount_cents / 100 if t.kind == "eft" else 0,
            f"=K{row-1}+G{row}-I{row}",
            t.amount_cents / 100 if t.kind == "cash" else 0,
            t.receipt_name,
        ]
        for col, value in enumerate(values, 1):
            ws.cell(row, col, value)
        ws.cell(row, 1).number_format = "dd/mm/yyyy"
    end = 10 + len(transactions)
    ws.cell(end + 2, 6, "Closing card balance")
    ws.cell(end + 2, 11, f"=K{end}")
    # Separate disclosure avoids treating requested money as money already loaded.
    ws.cell(
        end + 4,
        1,
        "Submitted card requests (await funding; excluded from card balance)",
    )
    requests = (
        []
        if blank
        else db.scalars(
            select(Requisition)
            .where(Requisition.month_id == month.id, Requisition.status == "submitted")
            .order_by(Requisition.id)
        ).all()
    )
    for r, req in enumerate(requests, end + 5):
        ws.cell(r, 1, req.number)
        ws.cell(r, 6, "Card amount requested")
        ws.cell(
            r,
            7,
            sum(
                line["amount_cents"]
                for line in json.loads(req.lines)
                if line["method"] == "card"
            )
            / 100,
        )
    form = wb.create_sheet("Requisition Forms")
    cursor = 1
    for req in requests or [None]:
        book = db.get(RequisitionBook, req.book_id) if req else None
        pairs = [
            ("Branch", branch_name),
            ("Date", str(req.request_date) if req else ""),
            ("Employee", req.employee_name if req else ""),
            ("Requisition number", req.number if req else ""),
            ("MF file", book.reference if book else ""),
            ("Deceased", book.deceased if book else ""),
        ]
        if req:
            pairs += [
                (k.replace("_", " ").title(), str(v))
                for k, v in json.loads(req.details).items()
            ]
        for label, value in pairs:
            form.cell(cursor, 1, label)
            form.cell(cursor, 2, value)
            cursor += 1
        start = cursor + 1
        form.cell(cursor, 1, "Payment requested")
        form.cell(cursor, 2, "Method")
        form.cell(cursor, 3, "Amount (ZAR)")
        cursor += 1
        for line in sorted(
            json.loads(req.lines) if req else [],
            key=lambda l: {"eft": 0, "cash": 1, "card": 2}[l["method"]],
        ):
            form.cell(cursor, 1, line["description"])
            form.cell(cursor, 2, line["method"].upper())
            form.cell(cursor, 3, line["amount_cents"] / 100)
            cursor += 1
        form.cell(cursor, 2, "TOTAL")
        form.cell(cursor, 3, f"=SUM(C{start}:C{cursor-1})" if cursor > start else 0)
        cursor += 4
    for sheet in wb:
        sheet.freeze_panes = "A11" if sheet == ws else "A1"
        for col in range(1, sheet.max_column + 1):
            sheet.column_dimensions[get_column_letter(col)].width = (
                24 if col != 6 else 44
            )
        sheet.column_dimensions["A"].width = 38
        for row in sheet:
            for cell in row:
                # Untrusted text must never become an Excel formula.
                if cell.data_type == "f" and not (
                    sheet == ws
                    and cell.column == 11
                    or sheet == form
                    and cell.column == 3
                    and cell.value.startswith("=SUM(")
                ):
                    cell.data_type = "s"
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if (
                    sheet == ws
                    and cell.row >= 10
                    and cell.column in (7, 9, 10, 11, 12)
                    or sheet == form
                    and cell.column == 3
                ):
                    cell.number_format = '"R "#,##0.00;[Red]-"R "#,##0.00'
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
    for cell in ws[9]:
        cell.fill = PatternFill("solid", fgColor="D2E5C0")
        cell.font = Font(bold=True)
    wb.calculation.fullCalcOnLoad = True
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def request_pdf(db, req, branch_name):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    book = db.get(RequisitionBook, req.book_id)
    styles = getSampleStyleSheet()
    out = BytesIO()
    p = lambda value: Paragraph(escape(str(value)), styles["BodyText"])
    content = [
        Paragraph("Requisition " + escape(req.number or "Draft"), styles["Title"])
    ]
    for key, value in [
        ("Branch", branch_name),
        ("Date", req.request_date),
        ("Employee", req.employee_name),
        ("MF file", book.reference),
        ("Deceased", book.deceased),
        *json.loads(req.details).items(),
    ]:
        content.append(p(f'{key.replace("_"," ").title()}: {value}'))
    content.append(Spacer(1, 16))
    rows = [["Payment requested", "Method", "Amount (ZAR)"]]
    for line in sorted(
        json.loads(req.lines),
        key=lambda l: {"eft": 0, "cash": 1, "card": 2}[l["method"]],
    ):
        rows.append(
            [
                p(line["description"]),
                line["method"].upper(),
                f"R {line['amount_cents']/100:,.2f}",
            ]
        )
    rows.append(["TOTAL", "", f"R {req.total_cents/100:,.2f}"])
    table = Table(rows, colWidths=[300, 65, 100], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D2E5C0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    content.append(table)
    SimpleDocTemplate(out).build(content)
    return out.getvalue()


def queue_email(db, month, branch_name, reason, req=None):
    db.flush()
    email = RequisitionEmail(
        month_id=month.id,
        subject=f"{branch_name} / {month.month} / {reason}",
        message=f"{reason}\nBranch: {branch_name}\nMonth: {month.month}\nCard balance: R {balance(db,month)/100:,.2f}\nAttached: updated monthly card transaction register and requisitions.",
        workbook=workbook_bytes(db, month, branch_name),
        document=request_pdf(db, req, branch_name) if req else None,
        status="pending",
        attempts=0,
        next_attempt_at=datetime.utcnow(),
    )
    db.add(email)
    db.flush()
    return email.id


def deliver_pending():
    from app.db.session import SessionLocal
    from app.services.email_service import send_smtp_email

    with SessionLocal() as db:
        ids = db.scalars(
            select(RequisitionEmail.id)
            .where(
                RequisitionEmail.status.in_(["pending", "failed"]),
                RequisitionEmail.next_attempt_at <= datetime.utcnow(),
            )
            .order_by(RequisitionEmail.id)
            .limit(20)
        ).all()
        for eid in ids:
            item = db.scalar(
                select(RequisitionEmail)
                .where(RequisitionEmail.id == eid)
                .with_for_update(skip_locked=True)
            )
            if not item or item.status not in ("pending", "failed"):
                continue
            item.status = "sending"
            item.attempts += 1
            db.commit()
            attachments = [
                (
                    f"card-transactions-{item.month_id}-{eid}.xlsx",
                    item.workbook,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            ]
            if item.document:
                attachments.append(
                    (f"requisition-{eid}.pdf", item.document, "application/pdf")
                )
            state, sent, error, diagnostics = send_smtp_email(
                RECIPIENT, item.subject, item.message, attachments=attachments
            )
            item.status = (
                "uncertain" if diagnostics.get("delivery_uncertain") else state
            )
            item.sent_at = sent
            item.error = error
            item.next_attempt_at = datetime.utcnow() + timedelta(minutes=15)
            db.commit()
        # An interrupted SMTP call cannot safely be retried automatically.
        # Persisted 'sending' and 'uncertain' records remain visible to the reviewer.
