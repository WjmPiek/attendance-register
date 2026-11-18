"""Shared mortuary upload, automatic monthly registers and report delivery."""

import calendar
from datetime import date, datetime, time
from sqlalchemy import select, text
from fastapi import HTTPException
from app.models.requisitions import (
    RequisitionMonth,
    RequisitionTransaction,
    RequisitionReportSetting,
    RequisitionMonthlyReport,
    Requisition,
)
from app.services import requisitions as service


def upload_scope(db, user, requested=None):
    try:
        return service.scope(db, user, requested)[0]
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
    from app.api.commission import _profile

    _, fid, _, _, kind = _profile(db, user)
    if kind not in {"employee", "manager"} or not fid or requested not in (None, fid):
        raise HTTPException(403, "Mortuary uploads are not enabled for this account.")
    active = db.execute(
        text(
            "SELECT 1 FROM employee_commission_options o JOIN franchise_users f ON f.id=o.franchise_user_id WHERE o.franchise_user_id=:fid AND o.employee_user_id=:uid AND o.enabled=TRUE AND f.is_active=TRUE LIMIT 1"
        ),
        {"fid": fid, "uid": user.id},
    ).scalar()
    if not active:
        raise HTTPException(
            403, "Mortuary uploads require active commissions or requisition access."
        )
    return fid


def stage_commission_book(db, fid, record, data, filename, actor):
    from app.services.commission_files import store_file
    from app.api.receipt_commissions import save_document

    store_file(
        db,
        fid,
        record["source_hash"],
        filename,
        data,
        actor,
        "mortuary",
        len(record.get("pages") or [record.get("page", 1)]),
    )
    save_document(db, fid, "mortuary", record, [], actor)


def ensure_month(db, fid, bid, day, holder, actor):
    service.branch(db, fid, bid)
    service.lock_branch(db, bid)
    key = day.strftime("%Y-%m")
    existing = db.scalar(
        select(RequisitionMonth).where(
            RequisitionMonth.branch_id == bid, RequisitionMonth.month == key
        )
    )
    if existing and existing.status == "open":
        return existing
    latest = db.scalar(
        select(RequisitionMonth)
        .where(RequisitionMonth.branch_id == bid)
        .order_by(RequisitionMonth.month.desc())
        .limit(1)
    )
    opening = 0
    if latest:
        if latest.month >= key:
            if latest.status == "open":
                return latest
            year, month = map(int, latest.month.split("-"))
            key = f"{year+(month==12):04d}-{month%12+1:02d}"
        if latest.status == "open":
            latest.closing_cents = service.balance(db, latest)
            latest.status = "closed"
        opening = latest.closing_cents
    item = RequisitionMonth(
        franchise_user_id=fid,
        branch_id=bid,
        month=key,
        holder=holder,
        opening_cents=opening,
        status="open",
        created_by=actor,
    )
    db.add(item)
    db.flush()
    # Unsubmitted work is still editable after the automatic month change.
    # Only drafts move; submitted forms and posted receipts remain historical.
    drafts = db.scalars(
        select(Requisition)
        .join(RequisitionMonth, Requisition.month_id == RequisitionMonth.id)
        .where(RequisitionMonth.branch_id == bid, Requisition.status == "draft")
    ).all()
    for draft in drafts:
        draft.month_id = item.id
        draft.request_date = (
            day if day.strftime("%Y-%m") == key else date.fromisoformat(key + "-01")
        )
    db.flush()
    return item


def allocate(db, req, month, actor, initial=False):
    rows = db.scalars(
        select(RequisitionTransaction).where(
            RequisitionTransaction.requisition_id == req.id,
            RequisitionTransaction.kind == "allocation",
        )
    ).all()
    if not rows and not initial:
        return
    delta = req.total_cents - sum(r.amount_cents for r in rows)
    if not delta:
        return
    if month.status != "open":
        from app.core.timezone import now_sa_naive

        month = ensure_month(
            db,
            month.franchise_user_id,
            month.branch_id,
            now_sa_naive().date(),
            month.holder,
            actor.id,
        )
    posted = max(req.request_date, date.fromisoformat(month.month + "-01"))
    name = service.branch(db, month.franchise_user_id, month.branch_id)["name"]
    db.add(
        RequisitionTransaction(
            month_id=month.id,
            requisition_id=req.id,
            client_key=f"allocation-{req.id}-{req.revision}",
            transaction_date=posted,
            kind="allocation",
            supplier="Requisition",
            description=f"{req.number} / Revision {req.revision}",
            amount_cents=delta,
            actor_id=actor.id,
            actor_name=actor.full_name,
            receipt_name=f"{req.number}.pdf",
            receipt_mime="application/pdf",
            receipt_content=service.request_pdf(db, req, name),
        )
    )
    db.flush()


def queue_monthly_reports(db, now=None):
    from app.core.timezone import now_sa_naive

    now = now or now_sa_naive()
    months = db.scalars(
        select(RequisitionMonth)
        .where(RequisitionMonth.month <= now.strftime("%Y-%m"))
        .order_by(RequisitionMonth.id)
    ).all()
    for month in months:
        year, number = map(int, month.month.split("-"))
        due = datetime.combine(
            date(year, number, min(30, calendar.monthrange(year, number)[1])), time(17)
        )
        if now < due:
            continue
        service.lock_branch(db, month.branch_id)
        if db.get(RequisitionMonthlyReport, month.id):
            continue
        setting = db.get(RequisitionReportSetting, month.franchise_user_id)
        name = service.branch(db, month.franchise_user_id, month.branch_id)["name"]
        eid = service.queue_email(
            db,
            month,
            name,
            "Monthly card transactions",
            recipient=setting.recipient if setting else service.RECIPIENT,
        )
        db.add(RequisitionMonthlyReport(month_id=month.id, email_id=eid))
        db.commit()
