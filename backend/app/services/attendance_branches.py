"""Holder-owned branches and explicit document-import delegation."""
from fastapi import HTTPException
from sqlalchemy import text
from app.services.receipt_commissions import branch_key


def branches(db, fid, active_only=True):
    return [dict(r) for r in db.execute(text('SELECT * FROM attendance_branches WHERE franchise_user_id=:fid AND NOT EXISTS (SELECT 1 FROM external_commission_branches x WHERE x.branch_id=attendance_branches.id)' + (' AND is_active=TRUE' if active_only else '') + ' ORDER BY name,id'), {'fid': fid}).mappings().all()]


def ensure_default_branch(db, fid):
    if not branches(db, fid, False):
        row = db.execute(text("SELECT COALESCE(NULLIF(franchise_name,''),NULLIF(business_name,''),'Unassigned branch') FROM franchise_users WHERE id=:fid"), {'fid': fid}).scalar()
        if row:
            db.execute(text('INSERT INTO attendance_branches(franchise_user_id,name) VALUES(:fid,:name)'), {'fid': fid, 'name': row})


def sync_branches(db, fid, scope):
    """Only the signed main-system handoff can supply authoritative group links."""
    existing = branches(db, fid, False)
    seen = []
    for item in scope:
        if not isinstance(item.get('id'), int) or not str(item.get('name') or '').strip():
            raise HTTPException(400, 'Invalid signed branch scope.')
        match = next((b for b in existing if b['main_franchise_id'] == item['id']), None)
        if not match:
            match = next((b for b in existing if b['main_franchise_id'] is None and branch_key(b['name']) == branch_key(item['name'])), None)
        if match:
            bid = match['id']
            db.execute(text('UPDATE attendance_branches SET name=:name,vat_number=:vat,main_franchise_id=:main,is_active=TRUE,main_synced=TRUE WHERE id=:id AND franchise_user_id=:fid'), {'id': bid, 'fid': fid, 'name': item['name'], 'main': item['id'], 'vat': item.get('vat_number')})
        else:
            bid = db.execute(text('INSERT INTO attendance_branches(franchise_user_id,main_franchise_id,name,vat_number,main_synced) VALUES(:fid,:main,:name,:vat,TRUE) RETURNING id'), {'fid': fid, 'main': item['id'], 'name': item['name'], 'vat': item.get('vat_number')}).scalar_one()
        seen.append(bid)
    for old in existing:
        if old['main_synced'] and old['id'] not in seen:
            db.execute(text('UPDATE attendance_branches SET is_active=FALSE WHERE id=:id'), {'id': old['id']})


def assignment(db, uid):
    row = db.execute(text('''SELECT a.*,b.name AS branch_name,b.is_active AS branch_active
        FROM employee_branch_assignments a JOIN attendance_branches b ON b.id=a.branch_id WHERE employee_user_id=:uid'''), {'uid': uid}).mappings().first()
    return dict(row) if row else None


def assign_staff(db, fid, uid, branch_id=None, can_import=None, creating=False):
    old = assignment(db, uid)
    if old and old['franchise_user_id'] != fid:
        raise HTTPException(403, 'Employee branch assignment belongs to another holder.')
    choices = branches(db, fid)
    branch_id = branch_id or (old['branch_id'] if old else choices[0]['id'] if len(choices) == 1 else None)
    if branch_id not in {b['id'] for b in choices}:
        raise HTTPException(400, 'Select an active branch belonging to this franchise holder.')
    flag = bool(can_import) if can_import is not None else bool(old and old['can_import_commissions'])
    db.execute(text('''INSERT INTO employee_branch_assignments(franchise_user_id,employee_user_id,branch_id,can_import_commissions)
        VALUES(:fid,:uid,:branch,:flag) ON CONFLICT(employee_user_id) DO UPDATE SET branch_id=EXCLUDED.branch_id,can_import_commissions=EXCLUDED.can_import_commissions'''),
        {'fid': fid, 'uid': uid, 'branch': branch_id, 'flag': flag})


def import_scope(db, user, requested=None):
    from app.api.commission import _profile
    from app.api.franchise_staff import _staff_franchise_id
    _, fid, _, _, kind = _profile(db, user)
    if kind in {'franchise', 'super'}:
        return _staff_franchise_id(db, user, requested)
    own = assignment(db, user.id)
    if not own or not own['can_import_commissions'] or not own['branch_active'] or own['franchise_user_id'] != fid or requested not in (None, fid):
        raise HTTPException(403, 'Commission document imports are not enabled for this staff member.')
    return fid


def import_staff(db, fid):
    return [dict(r) for r in db.execute(text('''SELECT s.*,a.branch_id,b.name AS branch_name,a.can_import_commissions FROM (
        SELECT e.user_id,e.franchise_user_id,COALESCE(NULLIF(TRIM(CONCAT(COALESCE(e.name,''),' ',COALESCE(e.surname,''))),''),u.full_name) AS full_name,
            e.employee_number,COALESCE(e.employee_role,'Employee') AS employee_role,'employee' AS staff_type,
            COALESCE(e.work_start_time,'08:00') AS work_start_time,COALESCE(e.work_end_time,'17:00') AS work_end_time,e.work_week
        FROM employee_users e JOIN users u ON u.id=e.user_id WHERE e.is_active=TRUE AND u.is_active=TRUE
        UNION ALL
        SELECT m.user_id,m.franchise_user_id,COALESCE(NULLIF(TRIM(CONCAT(COALESCE(m.name,''),' ',COALESCE(m.surname,''))),''),u.full_name),
            m.employee_number,'Manager','manager',COALESCE(m.work_start_time,'08:00'),COALESCE(m.work_end_time,'17:00'),m.work_week
        FROM manager_users m JOIN users u ON u.id=m.user_id WHERE m.is_active=TRUE AND u.is_active=TRUE
        ) s JOIN employee_branch_assignments a ON a.employee_user_id=s.user_id AND a.franchise_user_id=s.franchise_user_id
        JOIN attendance_branches b ON b.id=a.branch_id AND b.franchise_user_id=s.franchise_user_id
        WHERE s.franchise_user_id=:fid AND b.is_active=TRUE ORDER BY b.name,s.full_name'''), {'fid': fid}).mappings().all()]


def import_participant(db, user, uid, fid):
    # Import delegates can allocate across the holder's active branches, but do
    # not gain general permission to read or manage other employees' HR records.
    person = next((p for p in import_staff(db, fid) if p['user_id'] == uid), None)
    if not person:
        raise HTTPException(403, 'Employee is inactive or outside the holder branch group.')
    return person


def launch_branch_context(db,fid,handoff):
    selected=handoff.get('active_franchise_id')
    if not selected:
        return None
    match=next((b for b in branches(db,fid) if b['main_franchise_id']==selected),None)
    if not match:
        raise HTTPException(403,'Selected branch is outside this holder group.')
    return match['id']
