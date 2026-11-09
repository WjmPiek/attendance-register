"""Monthly commission statements, with pending evidence separate from payables."""

from sqlalchemy import text

from app.services.receipt_commissions import payment_eligibility


def pending_claims(db, fid, report):
    rows = db.execute(text('''SELECT c.*,u.full_name AS employee_name,b.name AS service_branch
        FROM commission_entries c JOIN users u ON u.id=c.employee_user_id
        LEFT JOIN attendance_branches b ON b.id=c.earning_branch_id
        WHERE c.franchise_user_id=:fid AND c.status IN ('pending','approved')
        AND COALESCE(c.is_cancelled,FALSE)=FALSE AND c.service_date<=:last
        AND NOT EXISTS(SELECT 1 FROM commission_monthly_report_items i WHERE i.entry_id=c.id)
        ORDER BY b.name,u.full_name,c.commission_type,c.service_date,c.id'''),
        {'fid':fid,'last':report['period_end']}).mappings().all()
    pending = []
    for row in rows:
        check = payment_eligibility(db,row)
        if row['status']=='approved' and check['payment_eligible']:
            continue
        pending.append({**dict(row), **check})
    return pending



def statement_pdf(rows, pending, report):
    from app.services.commission_pdf import build_commission_pdf
    return build_commission_pdf(rows,pending,title='Monthly commission statement',
        period_start=report['period_start'],period_end=report['period_end'],
        reference=f"Report #{report['id']} | Holder #{report['franchise_user_id']} | {report['month_key']}")
