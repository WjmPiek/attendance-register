"""Outside service evidence remains scoped to the importing franchise holder."""
from fastapi import HTTPException
from sqlalchemy import text


def external_branches(db, fid):
    return [dict(r) for r in db.execute(text('''SELECT b.* FROM attendance_branches b
        JOIN external_commission_branches x ON x.branch_id=b.id AND x.franchise_user_id=b.franchise_user_id
        WHERE b.franchise_user_id=:fid AND b.is_active=TRUE ORDER BY b.name,b.id'''), {'fid': fid}).mappings().all()]


def is_external(db, fid, bid):
    return bool(db.execute(text('SELECT 1 FROM external_commission_branches WHERE franchise_user_id=:fid AND branch_id=:bid'), {'fid': fid, 'bid': bid}).scalar())


def permission_branch(db, fid, uid, bid):
    if is_external(db, fid, bid):
        from app.services.attendance_branches import assignment
        own = assignment(db, uid)
        if not own or not own['branch_active'] or own['franchise_user_id'] != fid:
            raise HTTPException(403, 'Staff must belong to an active linked branch.')
        return own['branch_id']
    return bid


def outside_group(db, fid, name):
    from app.services.attendance_branches import branches
    from app.services.receipt_commissions import branch_key
    return branch_key(name) not in {branch_key(b['name']) for b in branches(db, fid)}
