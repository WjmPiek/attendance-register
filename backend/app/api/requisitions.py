"""Desktop web requisitions. Every record and file read enforces holder scope."""

from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import PurePath
from typing import Literal
from uuid import UUID
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_user_role_names
from app.db.session import get_db
from app.models.core import User
from app.models.requisitions import (
    RequisitionGrant,
    RequisitionSource,
    RequisitionBook,
    RequisitionMonth,
    Requisition,
    RequisitionTransaction,
    RequisitionEmail,
)
from app.services import requisitions as service

router = APIRouter()


class MonthIn(BaseModel):
    branch_id: int = Field(gt=0)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    holder: str = Field(min_length=1, max_length=255)
    opening_balance: Decimal = Field(
        default=0, ge=-10000000, le=10000000, decimal_places=2
    )


class GrantIn(BaseModel):
    user_id: int = Field(gt=0)
    enabled: bool


class CreateIn(BaseModel):
    month_id: int = Field(gt=0)
    book_id: int = Field(gt=0)
    request_date: date


class LineIn(BaseModel):
    description: str = Field(min_length=1, max_length=1000)
    method: Literal["eft", "cash", "card"]
    amount: Decimal = Field(gt=0, le=10000000, decimal_places=2)

    @field_validator("description")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Enter a payment description.")
        return value.strip()


class SaveIn(BaseModel):
    # Imported evidence remains immutable; additional fields are captured explicitly.
    details: dict[str, str] = Field(default_factory=dict, max_length=30)
    lines: list[LineIn] = Field(max_length=100)

    @field_validator("details")
    @classmethod
    def bounded_details(cls, value):
        if any(len(k) > 100 or len(v) > 1000 for k, v in value.items()):
            raise ValueError("Deceased detail fields are too long.")
        return value


class TransactionIn(BaseModel):
    requisition_id: int = Field(gt=0)
    client_key: UUID
    transaction_date: date
    kind: Literal["funding", "card", "eft", "cash"]
    supplier: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=1000)
    amount: Decimal = Field(gt=0, le=10000000, decimal_places=2)

    @field_validator("supplier", "description")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Supplier and description are required.")
        return value.strip()


def audit(db, user, fid, action, entity_id, values):
    from app.services.audit import write_audit_log

    write_audit_log(
        db,
        actor_user_id=user.id,
        franchise_user_id=fid,
        action=action,
        entity_type="requisition",
        entity_id=entity_id,
        new_values=values,
    )


def download(content, mime, filename):
    return Response(
        content=content,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def file_content(upload):
    data = upload.file.read(10 * 1024 * 1024 + 1)
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "Upload a nonempty receipt up to 10 MB.")
    mime = (
        "application/pdf"
        if data.startswith(b"%PDF-")
        else (
            "image/png"
            if data.startswith(b"\x89PNG\r\n\x1a\n")
            else "image/jpeg" if data.startswith(b"\xff\xd8\xff") else None
        )
    )
    if not mime:
        raise HTTPException(400, "Upload an original PDF, PNG or JPEG receipt.")
    name = PurePath((upload.filename or "receipt").replace("\\", "/")).name[:200]
    return data, mime, name


@router.get("/access")
def access(
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roles = get_user_role_names(db, current_user.id)
    holders = (
        [
            dict(r)
            for r in db.execute(
                text(
                    "SELECT id,COALESCE(NULLIF(franchise_name,''),business_name) AS name FROM franchise_users WHERE is_active=TRUE ORDER BY name"
                )
            ).mappings()
        ]
        if "SuperUser" in roles
        else []
    )
    if "SuperUser" in roles and not franchise_user_id:
        return {
            "enabled": True,
            "can_manage": True,
            "holders": holders,
            "branches": [],
            "franchise_user_id": None,
        }
    try:
        fid, admin = service.scope(db, current_user, franchise_user_id)
    except HTTPException as exc:
        if exc.status_code == 403 and franchise_user_id is None:
            return {
                "enabled": False,
                "can_manage": False,
                "branches": [],
                "holders": [],
            }
        raise
    from app.services.attendance_branches import branches
    from app.services.email_service import get_email_config

    return {
        "enabled": True,
        "can_manage": admin,
        "holders": holders,
        "franchise_user_id": fid,
        "branches": [{"id": b["id"], "name": b["name"]} for b in branches(db, fid)],
        "email_configured": get_email_config().configured,
        "recipient": service.RECIPIENT,
    }


@router.get("/staff")
def staff(
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id, manage=True)
    rows = db.execute(
        text("""SELECT DISTINCT u.id,u.full_name FROM users u JOIN (
        SELECT user_id FROM employee_users WHERE franchise_user_id=:fid AND is_active=TRUE
        UNION SELECT user_id FROM manager_users WHERE franchise_user_id=:fid AND is_active=TRUE
        ) s ON s.user_id=u.id WHERE u.is_active=TRUE ORDER BY u.full_name"""),
        {"fid": fid},
    ).mappings()
    allowed = set(
        db.scalars(
            select(RequisitionGrant.user_id).where(
                RequisitionGrant.franchise_user_id == fid
            )
        )
    )
    return [
        {"id": r["id"], "full_name": r["full_name"], "enabled": r["id"] in allowed}
        for r in rows
    ]


@router.put("/grants")
def grant(
    payload: GrantIn,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id, manage=True)
    choices = staff(franchise_user_id, current_user, db)
    if payload.user_id not in {r["id"] for r in choices}:
        raise HTTPException(403, "Select active staff in this holder group.")
    service.lock_branch(db, -fid)
    old = db.scalar(
        select(RequisitionGrant).where(
            RequisitionGrant.franchise_user_id == fid,
            RequisitionGrant.user_id == payload.user_id,
        )
    )
    if payload.enabled and not old:
        db.add(
            RequisitionGrant(
                franchise_user_id=fid,
                user_id=payload.user_id,
                granted_by=current_user.id,
            )
        )
    if not payload.enabled and old:
        db.delete(old)
    audit(
        db,
        current_user,
        fid,
        "requisition_access_changed",
        payload.user_id,
        payload.model_dump(),
    )
    db.commit()
    return {"saved": True}


@router.post("/books/import")
def import_book(
    branch_id: int,
    franchise_user_id: int | None = None,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id)
    selected = service.branch(db, fid, branch_id)
    data, mime, filename = file_content(file)
    if mime != "application/pdf":
        raise HTTPException(400, "Upload the original Mortuary Book PDF.")
    from app.services.mortuary import parse_pdf
    from app.services.receipt_commissions import branch_key

    try:
        records, errors = parse_pdf(data)
    except Exception:
        raise HTTPException(
            400, "Cannot read this Mortuary Book PDF. Use an unprotected original."
        )
    mismatches = [
        r for r in records if branch_key(r["branch"]) != branch_key(selected["name"])
    ]
    if errors or mismatches or not records:
        raise HTTPException(
            400,
            {
                "message": "No records imported. Check all pages and the selected branch.",
                "page_errors": errors,
                "wrong_branch_pages": [r.get("page") for r in mismatches],
            },
        )
    service.lock_branch(db, branch_id)
    items = []
    digest = sha256(data).hexdigest()
    # One original PDF can contain many MF files; retain its bytes only once.
    service.lock_branch(db, -fid)
    source = db.scalar(
        select(RequisitionSource).where(
            RequisitionSource.franchise_user_id == fid,
            RequisitionSource.sha256 == digest,
        )
    )
    if not source:
        source = RequisitionSource(
            franchise_user_id=fid, sha256=digest, filename=filename, content=data
        )
        db.add(source)
        db.flush()
    for record in records:
        reference = record["reference"].strip().upper()
        old = db.scalar(
            select(RequisitionBook).where(
                RequisitionBook.branch_id == branch_id,
                RequisitionBook.reference == reference,
            )
        )
        if old:
            if json.loads(old.details).get("deceased") != record.get("deceased"):
                raise HTTPException(
                    409,
                    "An imported MF file has different deceased details. Review the original book.",
                )
            items.append({"id": old.id, "reference": old.reference, "duplicate": True})
            continue
        item = RequisitionBook(
            franchise_user_id=fid,
            branch_id=branch_id,
            reference=reference,
            deceased=record.get("deceased", ""),
            details=json.dumps(record, default=str),
            source_id=source.id,
            uploaded_by=current_user.id,
        )
        db.add(item)
        db.flush()
        items.append({"id": item.id, "reference": reference, "duplicate": False})
    audit(
        db,
        current_user,
        fid,
        "requisition_book_imported",
        branch_id,
        {"sha256": sha256(data).hexdigest(), "records": items},
    )
    db.commit()
    return {"items": items}


@router.get("/books")
def books(
    branch_id: int,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id)
    service.branch(db, fid, branch_id)
    return [
        {
            "id": b.id,
            "reference": b.reference,
            "deceased": b.deceased,
            "details": json.loads(b.details),
        }
        for b in db.scalars(
            select(RequisitionBook)
            .where(
                RequisitionBook.branch_id == branch_id,
                RequisitionBook.franchise_user_id == fid,
            )
            .order_by(RequisitionBook.reference)
        )
    ]


@router.get("/books/{book_id}/file")
def book_file(
    book_id: int,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id)
    book = db.get(RequisitionBook, book_id)
    if not book or book.franchise_user_id != fid:
        raise HTTPException(404, "Book not found.")
    service.branch(db, fid, book.branch_id)
    source = db.get(RequisitionSource, book.source_id)
    return download(source.content, "application/pdf", f"mortuary-book-{book.id}.pdf")


@router.get("/months")
def months(
    branch_id: int,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id)
    service.branch(db, fid, branch_id)
    return [
        {
            "id": m.id,
            "month": m.month,
            "holder": m.holder,
            "status": m.status,
            "opening_cents": m.opening_cents,
            "balance_cents": service.balance(db, m),
        }
        for m in db.scalars(
            select(RequisitionMonth)
            .where(
                RequisitionMonth.branch_id == branch_id,
                RequisitionMonth.franchise_user_id == fid,
            )
            .order_by(RequisitionMonth.month.desc())
        )
    ]


@router.post("/months")
def create_month(
    payload: MonthIn,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id, manage=True)
    service.branch(db, fid, payload.branch_id)
    service.lock_branch(db, payload.branch_id)
    try:
        date.fromisoformat(payload.month + "-01")
    except ValueError:
        raise HTTPException(400, "Select a valid month.")
    previous = db.scalar(
        select(RequisitionMonth)
        .where(RequisitionMonth.branch_id == payload.branch_id)
        .order_by(RequisitionMonth.month.desc())
        .limit(1)
    )
    opening = service.cents(payload.opening_balance)
    if previous:
        expected = f'{int(previous.month[:4])+(previous.month[5:] == "12"):04d}-{int(previous.month[5:])%12+1:02d}'
        if previous.status != "closed" or payload.month != expected:
            raise HTTPException(
                409,
                "Close the latest month, then create the immediately following month.",
            )
        opening = previous.closing_cents
    item = RequisitionMonth(
        franchise_user_id=fid,
        branch_id=payload.branch_id,
        month=payload.month,
        holder=payload.holder.strip(),
        opening_cents=opening,
        status="open",
        created_by=current_user.id,
    )
    if not item.holder:
        raise HTTPException(400, "Enter the card holder name.")
    db.add(item)
    db.flush()
    audit(
        db,
        current_user,
        fid,
        "requisition_month_created",
        item.id,
        {"month": item.month, "opening_cents": opening},
    )
    db.commit()
    return {"id": item.id}


@router.get("/months/{month_id}")
def month_detail(
    month_id: int,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, admin = service.scope(db, current_user, franchise_user_id)
    m = service.month_row(db, fid, month_id)
    reqs = db.scalars(
        select(Requisition).where(Requisition.month_id == m.id).order_by(Requisition.id)
    ).all()
    tx = db.scalars(
        select(RequisitionTransaction)
        .where(RequisitionTransaction.month_id == m.id)
        .order_by(RequisitionTransaction.transaction_date, RequisitionTransaction.id)
    ).all()
    emails = db.scalars(
        select(RequisitionEmail)
        .where(RequisitionEmail.month_id == m.id)
        .order_by(RequisitionEmail.id.desc())
        .limit(30)
    ).all()
    running = m.opening_cents
    transactions = []
    for t in tx:
        running += (
            t.amount_cents
            if t.kind == "funding"
            else -t.amount_cents if t.kind == "card" else 0
        )
        transactions.append(
            {
                "id": t.id,
                "requisition_id": t.requisition_id,
                "number": db.get(Requisition, t.requisition_id).number,
                "transaction_date": str(t.transaction_date),
                "kind": t.kind,
                "supplier": t.supplier,
                "description": t.description,
                "amount_cents": t.amount_cents,
                "actor_name": t.actor_name,
                "receipt_name": t.receipt_name,
                "balance_cents": running,
            }
        )
    return {
        "id": m.id,
        "month": m.month,
        "branch_id": m.branch_id,
        "holder": m.holder,
        "status": m.status,
        "opening_cents": m.opening_cents,
        "balance_cents": running,
        "requisitions": [service.req_data(db, r) for r in reqs],
        "transactions": transactions,
        "emails": [
            {
                "id": e.id,
                "subject": e.subject,
                "status": e.status,
                "sent_at": e.sent_at,
                "error": (
                    e.error
                    if admin
                    else ("Delivery pending review" if e.error else None)
                ),
            }
            for e in emails
        ],
    }


@router.get("/submitted")
def submitted(
    branch_id: int,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id)
    service.branch(db, fid, branch_id)
    items = db.scalars(
        select(Requisition)
        .join(RequisitionMonth, Requisition.month_id == RequisitionMonth.id)
        .where(
            RequisitionMonth.franchise_user_id == fid,
            RequisitionMonth.branch_id == branch_id,
            Requisition.status == "submitted",
        )
        .order_by(Requisition.id.desc())
    )
    return [
        {
            "id": r.id,
            "number": r.number,
            "reference": db.get(RequisitionBook, r.book_id).reference,
        }
        for r in items
    ]


@router.post("/emails/{email_id}/retry")
def retry_email(
    email_id: int,
    background_tasks: BackgroundTasks,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id, manage=True)
    item = db.get(RequisitionEmail, email_id)
    if not item:
        raise HTTPException(404, "Email not found.")
    service.month_row(db, fid, item.month_id)
    service.lock_branch(db, -fid)
    db.refresh(item)
    if item.status not in ("failed", "pending"):
        raise HTTPException(
            409, "Check delivery before resending a sent, sending or uncertain email."
        )
    item.next_attempt_at = datetime.utcnow()
    db.commit()
    background_tasks.add_task(service.deliver_pending)
    return {"queued": True}


@router.post("/requests")
def create_request(
    payload: CreateIn,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id)
    m = service.month_row(db, fid, payload.month_id, True)
    book = db.get(RequisitionBook, payload.book_id)
    if not book or book.franchise_user_id != fid or book.branch_id != m.branch_id:
        raise HTTPException(403, "Choose a Mortuary Book from this branch.")
    if payload.request_date.strftime("%Y-%m") != m.month:
        raise HTTPException(400, "Requisition date must be inside the selected month.")
    # Recover an existing empty draft after a double click or lost response.
    item = db.scalar(
        select(Requisition).where(
            Requisition.month_id == m.id,
            Requisition.book_id == book.id,
            Requisition.employee_id == current_user.id,
            Requisition.status == "draft",
        )
    )
    if not item:
        details = {
            k: str(v)
            for k, v in json.loads(book.details).items()
            if k in ("id_number", "collected_at", "date_in", "time_in", "service_date")
        }
        item = Requisition(
            month_id=m.id,
            book_id=book.id,
            employee_id=current_user.id,
            employee_name=current_user.full_name,
            request_date=payload.request_date,
            details=json.dumps(details),
            lines="[]",
            total_cents=0,
            status="draft",
        )
        db.add(item)
        db.flush()
        audit(
            db,
            current_user,
            fid,
            "requisition_draft_created",
            item.id,
            {"book_id": book.id},
        )
        db.commit()
    return service.req_data(db, item)


@router.get("/requests/{request_id}")
def request_detail(
    request_id: int,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id)
    req, _ = service.request_row(db, fid, request_id)
    return service.req_data(db, req)


@router.put("/requests/{request_id}")
def save_request(
    request_id: int,
    payload: SaveIn,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, admin = service.scope(db, current_user, franchise_user_id)
    req, _ = service.request_row(db, fid, request_id, True)
    if req.status != "draft":
        raise HTTPException(
            409,
            "Submitted requisitions are immutable. Create another application for additional services.",
        )
    if req.employee_id != current_user.id and not admin:
        raise HTTPException(403, "Only the author or holder can edit this draft.")
    lines = [
        {
            "description": l.description,
            "method": l.method,
            "amount_cents": service.cents(l.amount),
        }
        for l in payload.lines
    ]
    if sum(l["amount_cents"] for l in lines) > 1000000000:
        raise HTTPException(400, "Requisition total exceeds R10 million.")
    req.lines = json.dumps(lines)
    req.details = json.dumps(payload.details)
    req.total_cents = sum(l["amount_cents"] for l in lines)
    audit(
        db,
        current_user,
        fid,
        "requisition_draft_saved",
        req.id,
        {"total_cents": req.total_cents},
    )
    db.commit()
    return service.req_data(db, req)


@router.delete("/requests/{request_id}")
def discard_draft(
    request_id: int,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, admin = service.scope(db, current_user, franchise_user_id)
    req, _ = service.request_row(db, fid, request_id, True)
    if req.status != "draft":
        raise HTTPException(409, "Submitted financial records cannot be deleted.")
    if req.employee_id != current_user.id and not admin:
        raise HTTPException(403, "Only the author or holder can discard this draft.")
    audit(
        db,
        current_user,
        fid,
        "requisition_draft_discarded",
        req.id,
        service.req_data(db, req),
    )
    db.delete(req)
    db.commit()
    return {"discarded": True}


@router.post("/requests/{request_id}/submit")
def submit_request(
    request_id: int,
    background_tasks: BackgroundTasks,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, admin = service.scope(db, current_user, franchise_user_id)
    req, m = service.request_row(db, fid, request_id, True)
    if req.employee_id != current_user.id and not admin:
        raise HTTPException(403, "Only the author or holder can submit this draft.")
    if req.status == "submitted":
        return service.req_data(db, req)
    if not json.loads(req.lines) or req.total_cents <= 0:
        raise HTTPException(400, "Add at least one payment before submitting.")
    req.number = f"REQ-{m.branch_id}-{m.month[:4]}-{req.id:06d}"
    req.status = "submitted"
    req.submitted_at = datetime.utcnow()
    name = service.branch(db, fid, m.branch_id)["name"]
    service.queue_email(db, m, name, "Submitted " + req.number, req)
    audit(
        db,
        current_user,
        fid,
        "requisition_submitted",
        req.id,
        {"number": req.number, "total_cents": req.total_cents},
    )
    db.commit()
    background_tasks.add_task(service.deliver_pending)
    return service.req_data(db, req)


@router.post("/transactions")
def post_transaction(
    background_tasks: BackgroundTasks,
    payload: str = Form(...),
    receipt: UploadFile = File(...),
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = TransactionIn.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(422, str(exc))
    fid, _ = service.scope(
        db, current_user, franchise_user_id, manage=data.kind in ("funding", "eft")
    )
    req, request_month = service.request_row(db, fid, data.requisition_id)
    if req.status != "submitted":
        raise HTTPException(409, "Submit the requisition before posting transactions.")
    # A receipt can belong to a later calendar month than its original application.
    m = db.scalar(
        select(RequisitionMonth).where(
            RequisitionMonth.branch_id == request_month.branch_id,
            RequisitionMonth.month == data.transaction_date.strftime("%Y-%m"),
        )
    )
    if not m:
        raise HTTPException(
            409, "Create the monthly register for the receipt date first."
        )
    m = service.month_row(db, fid, m.id, True)
    content, mime, name = file_content(receipt)
    existing = db.scalar(
        select(RequisitionTransaction).where(
            RequisitionTransaction.month_id == m.id,
            RequisitionTransaction.client_key == str(data.client_key),
        )
    )
    if existing:
        if (
            existing.requisition_id,
            existing.transaction_date,
            existing.kind,
            existing.supplier,
            existing.description,
            existing.amount_cents,
            sha256(existing.receipt_content).digest(),
        ) != (
            req.id,
            data.transaction_date,
            data.kind,
            data.supplier,
            data.description,
            service.cents(data.amount),
            sha256(content).digest(),
        ):
            raise HTTPException(
                409,
                "This transaction was already posted with different details. Refresh the register before entering another payment.",
            )
        return {"id": existing.id, "duplicate": True}
    item = RequisitionTransaction(
        month_id=m.id,
        requisition_id=req.id,
        client_key=str(data.client_key),
        transaction_date=data.transaction_date,
        kind=data.kind,
        supplier=data.supplier,
        description=data.description,
        amount_cents=service.cents(data.amount),
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        receipt_name=name,
        receipt_mime=mime,
        receipt_content=content,
    )
    db.add(item)
    db.flush()
    service.queue_email(
        db,
        m,
        service.branch(db, fid, m.branch_id)["name"],
        f"{data.kind.title()} recorded / {req.number}",
    )
    audit(
        db,
        current_user,
        fid,
        "requisition_transaction_posted",
        item.id,
        {
            "kind": data.kind,
            "requisition_id": req.id,
            "amount_cents": item.amount_cents,
            "receipt_sha256": sha256(content).hexdigest(),
        },
    )
    db.commit()
    background_tasks.add_task(service.deliver_pending)
    return {"id": item.id, "duplicate": False}


@router.get("/transactions/{transaction_id}/receipt")
def receipt_file(
    transaction_id: int,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id)
    item = db.get(RequisitionTransaction, transaction_id)
    if not item:
        raise HTTPException(404, "Receipt not found.")
    service.month_row(db, fid, item.month_id)
    extension = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}[
        item.receipt_mime
    ]
    return download(
        item.receipt_content, item.receipt_mime, f"receipt-{item.id}.{extension}"
    )


@router.post("/months/{month_id}/close")
def close_month(
    month_id: int,
    background_tasks: BackgroundTasks,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id, manage=True)
    m = service.month_row(db, fid, month_id, True)
    if db.scalar(
        select(Requisition.id)
        .where(Requisition.month_id == m.id, Requisition.status == "draft")
        .limit(1)
    ):
        raise HTTPException(409, "Submit all drafts before closing the month.")
    m.closing_cents = service.balance(db, m)
    m.status = "closed"
    service.queue_email(
        db, m, service.branch(db, fid, m.branch_id)["name"], "Month closed"
    )
    audit(
        db,
        current_user,
        fid,
        "requisition_month_closed",
        m.id,
        {"closing_cents": m.closing_cents},
    )
    db.commit()
    background_tasks.add_task(service.deliver_pending)
    return {"closing_cents": m.closing_cents}


@router.get("/months/{month_id}/workbook")
def workbook(
    month_id: int,
    blank: bool = False,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id)
    m = service.month_row(db, fid, month_id)
    b = service.branch(db, fid, m.branch_id)
    return download(
        service.workbook_bytes(db, m, b["name"], blank),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        f'{"blank" if blank else "card-transactions"}-branch-{m.branch_id}-{m.month}.xlsx',
    )


@router.get("/requests/{request_id}/pdf")
def pdf(
    request_id: int,
    franchise_user_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fid, _ = service.scope(db, current_user, franchise_user_id)
    req, m = service.request_row(db, fid, request_id)
    return download(
        service.request_pdf(db, req, service.branch(db, fid, m.branch_id)["name"]),
        "application/pdf",
        f"requisition-{req.id}.pdf",
    )
