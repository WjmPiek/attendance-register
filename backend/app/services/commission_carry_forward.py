"""Durable, once-per-cycle carry-forward records and staff notifications."""
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import text


# Use the current earning cycle for filtering while preserving the actual service
# date on the claim. Delivered statements and original evidence are never rewritten.
EARNING_DATE_SQL = '''COALESCE((SELECT cf.target_end FROM commission_carry_forwards cf
    WHERE cf.entry_id=c.id ORDER BY cf.target_month DESC LIMIT 1),c.service_date)'''


def month_label(value):
    return datetime.strptime(value,'%Y-%m').strftime('%B %Y')


def carry_info(db, entry_id):
    row=db.execute(text('''SELECT source_month,target_month FROM commission_carry_forwards
        WHERE entry_id=:id ORDER BY target_month DESC LIMIT 1'''),{'id':entry_id}).mappings().first()
    if not row:
        return {}
    return {'carried_from_month':row['source_month'],'carried_to_month':row['target_month'],
            'carry_forward_notice':f"Carried over from {month_label(row['source_month'])} into {month_label(row['target_month'])}."}


def carry_pending_claims(db, fid, report, pending):
    if not pending:
        return
    from app.services.commission_automation import ensure_month_report
    from app.api.commission import _notify, _audit
    following=(datetime.strptime(report['month_key'],'%Y-%m').replace(day=28)+timedelta(days=4)).replace(day=1)
    ensure_month_report(db,fid,following)
    target=db.execute(text('''SELECT * FROM commission_monthly_reports
        WHERE franchise_user_id=:fid AND month_key=:month'''),{'fid':fid,'month':following.strftime('%Y-%m')}).mappings().one()
    # If an old failed delivery is retried, never move a claim backwards.
    while target['status'] in {'sent','sending','uncertain'}:
        following=(following.replace(day=28)+timedelta(days=4)).replace(day=1)
        ensure_month_report(db,fid,following)
        target=db.execute(text('SELECT * FROM commission_monthly_reports WHERE franchise_user_id=:fid AND month_key=:month'),
                          {'fid':fid,'month':following.strftime('%Y-%m')}).mappings().one()
    owner=db.execute(text('SELECT user_id FROM franchise_users WHERE id=:fid'),{'fid':fid}).scalar()
    for row in pending:
        latest=carry_info(db,row['id'])
        if latest and latest['carried_to_month']>report['month_key']:
            continue
        estimate=None if row.get('estimate_available') is False else Decimal(str(row.get('expected_amount',row['calculated_amount']) or 0))
        inserted=db.execute(text('''INSERT INTO commission_carry_forwards(entry_id,source_report_id,source_month,
            target_month,target_start,target_end,estimated_amount,reason)
            VALUES(:id,:report,:source,:target,:first,:last,:amount,:reason)
            ON CONFLICT(entry_id,source_report_id) DO NOTHING RETURNING entry_id'''),
            {'id':row['id'],'report':report['id'],'source':report['month_key'],'target':target['month_key'],
             'first':target['period_start'],'last':target['period_end'],'amount':estimate,
             'reason':row.get('payment_block_reason') or 'Awaiting document checks'}).scalar()
        if not inserted:
            continue
        notice=carry_info(db,row['id'])['carry_forward_notice']
        amount=f'Estimated R {estimate:,.2f}' if estimate is not None else 'Amount awaiting document checks'
        ready=row['status']=='approved' and row.get('payment_eligible')
        explanation='Verified and included in that cycle’s approved total.' if ready else 'Not approved for payment. It will be added to that cycle’s approved total only when the required documents match and the invoice is fully paid.'
        message=f"MF {row['reference']} · {row.get('service_branch') or row.get('branch_name') or ''} · {amount}. {notice} {explanation}"
        for uid in {row['employee_user_id'],owner}-{None}:
            _notify(db,uid,'Commission carried forward',message,row['id'],'warning')
        _audit(db,row['id'],'commission_carried_forward',owner,new={'from_month':report['month_key'],
               'to_month':target['month_key'],'estimated_amount':str(estimate) if estimate is not None else None},note=message)


def carry_after_cutoff(db, fid, row):
    """A late submission/approval belongs to an open cycle, even on cutoff day."""
    report=db.execute(text('''SELECT r.* FROM commission_monthly_reports r
        WHERE r.franchise_user_id=:fid AND r.period_end>=:day
        AND (r.status IN ('sent','sending','uncertain') OR r.pdf_content IS NOT NULL)
        AND NOT EXISTS(SELECT 1 FROM commission_monthly_report_items i WHERE i.entry_id=:entry)
        ORDER BY r.month_key DESC LIMIT 1'''),{'fid':fid,'day':row['service_date'],'entry':row['id']}).mappings().first()
    if report:
        carry_pending_claims(db,fid,report,[row])
