"""Money is integer cents; posted funding, card purchases and EFTs affect balance."""

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
    RequisitionRevision,
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


def assign_request_number(req):
    """Allocate once to the original employee; submission never renumbers it."""
    if not req.number:
        req.number = f"REQ-{req.employee_id}-{req.request_date.year}-{req.id:06d}"
    return req.number


def priced_lines(req):
    return [
        line for line in json.loads(req.lines) if (line.get("amount_cents") or 0) > 0
    ]


def record_revision(db, req, actor_id):
    if not db.scalar(
        select(RequisitionRevision.id).where(
            RequisitionRevision.requisition_id == req.id,
            RequisitionRevision.revision == req.revision,
        )
    ):
        db.add(
            RequisitionRevision(
                requisition_id=req.id,
                revision=req.revision,
                actor_id=actor_id,
                snapshot=json.dumps(req_data(db, req)),
            )
        )


def balance(db, month):
    rows = db.scalars(
        select(RequisitionTransaction).where(
            RequisitionTransaction.month_id == month.id
        )
    ).all()
    return month.opening_cents + sum(
        (
            t.amount_cents
            if t.kind in {"funding", "allocation"}
            else -t.amount_cents if t.kind in {"card", "eft", "cash_payment"} else 0
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
        "revision": req.revision,
        "reference": book.reference,
        "deceased": book.deceased,
        "details": json.loads(req.details),
        "lines": json.loads(req.lines),
        "total_cents": req.total_cents,
    }


def workbook_bytes(db, month, branch_name, blank=False):
    from app.services.requisition_workbook import export_workbook

    return export_workbook(db, month, branch_name, blank)


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
    content.append(p(f"Status: {req.status.title()}"))
    if req.revision:
        content.append(p(f"Revision: {req.revision}"))
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
    rows = [["Expense", "Payment requested", "Method", "Amount (ZAR)"]]
    for line in sorted(
        priced_lines(req),
        key=lambda l: {"eft": 0, "cash": 1, "card": 2}[l["method"]],
    ):
        rows.append(
            [
                p(line.get("category", "")),
                p(line["description"]),
                line["method"].upper(),
                f"R {line['amount_cents']/100:,.2f}",
            ]
        )
    rows.append(["TOTAL", "", "", f"R {req.total_cents/100:,.2f}"])
    table = Table(rows, colWidths=[85, 235, 55, 90], repeatRows=1)
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


def queue_email(db, month, branch_name, reason, req=None, recipient=None):
    db.flush()
    email = RequisitionEmail(
        month_id=month.id,
        subject=f"{branch_name} / {month.month} / {reason}",
        message=f"{reason}\nBranch: {branch_name}\nMonth: {month.month}\nCard balance: R {balance(db,month)/100:,.2f}\nAttached: "
        + (
            "requisition PDF."
            if req
            else "monthly card transaction register and requisitions."
        ),
        workbook=workbook_bytes(db, month, branch_name),
        document=request_pdf(db, req, branch_name) if req else None,
        status="pending",
        attempts=0,
        next_attempt_at=datetime.utcnow(),
        recipient=recipient or RECIPIENT,
        include_workbook=req is None,
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
            attachments = (
                [
                    (
                        f"card-transactions-{item.month_id}-{eid}.xlsx",
                        item.workbook,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                ]
                if item.include_workbook
                else []
            )
            if item.document:
                attachments.append(
                    (f"requisition-{eid}.pdf", item.document, "application/pdf")
                )
            state, sent, error, diagnostics = send_smtp_email(
                item.recipient, item.subject, item.message, attachments=attachments
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
