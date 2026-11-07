"""Approve only verified commissions; keep external payroll separate."""
import json
import logging
from datetime import datetime, timedelta
from types import SimpleNamespace

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import HTTPException
from sqlalchemy import text

from app.core.timezone import now_sa_naive
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone='Africa/Johannesburg')
FINANCE_RECIPIENTS = 'wjm@martinsdirect.com, finance@martinsdirect.com'


def auto_approve_holder(db, fid, document_ids=None):
    from app.api.commission import EntryIn, ReviewIn, _review_service
    from app.api.receipt_commissions import calculate_plan, store_ready_plan
    owner = db.execute(text('''SELECT f.user_id FROM franchise_users f JOIN users u ON u.id=f.user_id
        WHERE f.id=:fid AND COALESCE(f.is_active,TRUE)=TRUE AND COALESCE(u.is_active,TRUE)=TRUE'''), {'fid': fid}).scalar()
    if not owner:
        return 0
    actor = SimpleNamespace(id=owner)
    db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'), {'namespace': 15015, 'fid': fid})
    count = 0
    pending = db.execute(text("SELECT * FROM commission_entries WHERE franchise_user_id=:fid AND status='pending' AND COALESCE(is_cancelled,FALSE)=FALSE ORDER BY id"), {'fid': fid}).mappings().all()
    for row in pending:
        meta = json.loads(row.get('source_metadata') or '{}')
        if not meta.get('claim_deceased'):
            continue  # Legacy entries need their missing claim details completed.
        values = {key: row[key] for key in EntryIn.model_fields if key in row}
        values.update(claim_deceased=meta['claim_deceased'], commission_role=meta.get('commission_role', 'driver'))
        try:
            with db.begin_nested():
                _review_service(row['id'], ReviewIn(**values, status='approved', review_notes='Automatically approved: matching documents and fully paid invoice.'), actor, db, automatic=True)
            count += 1
        except HTTPException:
            continue  # Missing proof, changed eligibility or rate: remain blocked.
    if document_ids is None:
        document_ids = db.execute(text('SELECT id FROM commission_documents WHERE franchise_user_id=:fid AND deleted_at IS NULL'), {'fid': fid}).scalars().all()
    if document_ids:
        plan = calculate_plan(db, fid, document_ids, actor)
        count += len(store_ready_plan(db, fid, actor, plan, automatic=True))
    return count


def default_report(now=None):
    now = now or now_sa_naive()
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous = first - timedelta(days=1)
    return {'month_key': now.strftime('%Y-%m'), 'period_start': previous.date().replace(day=26),
            'period_end': now.date().replace(day=25), 'send_on': first.replace(day=25, hour=17), 'status': 'scheduled'}


def ensure_month_report(db, fid, now):
    defaults = default_report(now)
    db.execute(text('''INSERT INTO commission_monthly_reports(franchise_user_id,month_key,period_start,period_end,send_on)
        VALUES(:fid,:month_key,:period_start,:period_end,:send_on) ON CONFLICT(franchise_user_id,month_key) DO NOTHING'''),
        {'fid': fid, **{key: defaults[key] for key in ('month_key', 'period_start', 'period_end', 'send_on')}})


def report_content(db, fid, report):
    from app.services.receipt_commissions import payment_eligibility
    # Every delivered entry is reserved permanently. Late evidence is included
    # as an earlier-period adjustment instead of disappearing after cutoff.
    rows = db.execute(text('''SELECT c.*,u.full_name AS employee_name,b.name AS service_branch FROM commission_entries c
        JOIN users u ON u.id=c.employee_user_id LEFT JOIN attendance_branches b ON b.id=c.earning_branch_id
        WHERE c.franchise_user_id=:fid AND c.status='approved' AND COALESCE(c.is_cancelled,FALSE)=FALSE
        AND c.service_date<=:last AND NOT EXISTS (SELECT 1 FROM commission_monthly_report_items i WHERE i.entry_id=c.id)
        ORDER BY u.full_name,c.service_date,c.id'''), {'fid': fid, 'last': report['period_end']}).mappings().all()
    rows = [dict(row) for row in rows if payment_eligibility(db, row)['payment_eligible']]
    from decimal import Decimal
    totals = {}
    details = []
    for row in rows:
        uid = row['employee_user_id']
        totals.setdefault(uid, {'name': row['employee_name'], 'total': Decimal(0)})['total'] += Decimal(str(row['calculated_amount']))
        earlier = str(row['service_date']) < str(report['period_start'])
        details.append(f"#{row['id']} | {row['employee_name']} | {row['service_date']} | {row['service_branch'] or row.get('branch_name') or ''} | {row['commission_type'].replace('_', ' ')} | MF {row['reference']} | R {Decimal(str(row['calculated_amount'])):,.2f}" + (' | Earlier-period adjustment' if earlier else ''))
    total = sum((item['total'] for item in totals.values()), Decimal(0))
    subject = f"Approved commission summary {report['month_key']} — report #{report['id']}"
    message = '\n'.join([
        f"Commission report #{report['id']}", f"Cycle: {report['period_start']} to {report['period_end']}",
        f"Prepared: {now_sa_naive():%Y-%m-%d %H:%M} South African time", '',
        'Approved commissions for processing by your finance team. This is a commission statement; it does not execute payroll or transfer funds.',
        'Each entry is included in one monthly summary only, including overlapping cutoff dates. Late approvals from earlier periods are carried forward.', '',
        *[f"{item['name']}: R {item['total']:,.2f}" for item in totals.values()], f"TOTAL: R {total:,.2f}", '',
        'DETAILS', *(details or ['No newly reportable approved commissions.']), '',
        f"Use report #{report['id']} as the unique processing reference. Do not process the same report twice.",
    ])
    return rows, subject, message


def send_due_reports(db, fid, now=None):
    from app.services.email_service import send_smtp_email
    now = now or now_sa_naive()
    db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'), {'namespace': 15016, 'fid': fid})
    ensure_month_report(db, fid, now)
    reports = db.execute(text("""SELECT * FROM commission_monthly_reports WHERE franchise_user_id=:fid
        AND status IN ('scheduled','failed','pending') AND send_on<=:now
        AND (next_attempt_at IS NULL OR next_attempt_at<=:now) ORDER BY send_on,id"""), {'fid': fid, 'now': now}).mappings().all()
    for report in reports:
        db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'), {'namespace': 15016, 'fid': fid})
        current_status = db.execute(text('SELECT status FROM commission_monthly_reports WHERE id=:id'), {'id': report['id']}).scalar_one()
        if current_status not in {'scheduled', 'failed', 'pending'}:
            continue
        rows, subject, message = report_content(db, fid, report)
        from app.services.commission_statement import statement_pdf, pending_claims
        pending = pending_claims(db,fid,report)
        pdf = statement_pdf(rows,pending,report)
        # Commit a durable sending marker first. If a process dies after SMTP
        # accepts the message, never retry blindly and duplicate a finance report.
        db.execute(text("""UPDATE commission_monthly_reports SET status='sending',recipient_email=:email,
            subject=:subject,message=:message,pdf_content=:pdf,error_message=NULL WHERE id=:id"""),
            {'email': FINANCE_RECIPIENTS, 'subject': subject, 'message': message, 'pdf':pdf, 'id': report['id']})
        for row in rows:
            db.execute(text('INSERT INTO commission_monthly_report_items(entry_id,report_id) VALUES(:entry,:report)'), {'entry': row['id'], 'report': report['id']})
        db.commit()
        status, sent_at, error, diagnostics = send_smtp_email(FINANCE_RECIPIENTS, subject, message,
            attachments=[(f"commission-statement-{report['month_key']}-{fid}-{report['id']}.pdf",pdf,'application/pdf')])
        if diagnostics.get('delivery_uncertain'):
            status = 'uncertain'
        if status not in {'sent', 'uncertain'}:
            db.execute(text('DELETE FROM commission_monthly_report_items WHERE report_id=:id'), {'id': report['id']})
        db.execute(text('''UPDATE commission_monthly_reports SET status=:status,sent_at=:sent,error_message=:error,
            next_attempt_at=:next WHERE id=:id'''), {'status': status, 'sent': sent_at, 'error': error, 'next': None if status == 'sent' else now + timedelta(hours=1), 'id': report['id']})
        db.commit()


def reconcile_holder(fid):
    try:
        with SessionLocal() as db:
            auto_approve_holder(db, fid)
            db.commit()
    except Exception:
        logger.exception('Commission reconciliation queued for retry for holder %s', fid)


def run_automation():
    with SessionLocal() as db:
        holders = db.execute(text('SELECT id FROM franchise_users WHERE COALESCE(is_active,TRUE)=TRUE')).scalars().all()
    for fid in holders:
        try:
            with SessionLocal() as db:
                auto_approve_holder(db, fid)
                db.commit()
                send_due_reports(db, fid)
        except Exception:
            logger.exception('Commission reconciliation or summary delivery failed for holder %s', fid)


def start_automation():
    if not scheduler.running:
        scheduler.add_job(run_automation, 'interval', seconds=60, id='commission-reconciliation', max_instances=1,
                          coalesce=True, replace_existing=True, next_run_time=now_sa_naive() + timedelta(seconds=5))
        scheduler.start()
        from app.services.email_service import get_email_config
        # Operational confirmation without logging credentials or recipient data.
        logging.getLogger('uvicorn.error').info(
            'Commission automation started: reconciliation every 60 seconds; default PDF delivery on the 25th at 17:00 SA; SMTP configured=%s',
            get_email_config().configured)


def stop_automation():
    if scheduler.running:
        scheduler.shutdown(wait=False)

