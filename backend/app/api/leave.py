from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.core import User, UserRole
from app.core.timezone import now_sa_naive, format_sa_date
from app.services.notification_service import create_notification

router = APIRouter()


def _roles(db: Session, user: User) -> set[str]:
    return {ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()}


def _ensure_tables(db: Session):
    db.execute(text('''
        CREATE TABLE IF NOT EXISTS leave_applications (
            id SERIAL PRIMARY KEY,
            applicant_user_id INTEGER NOT NULL,
            employee_user_id INTEGER NULL,
            franchise_user_id INTEGER NULL,
            manager_user_id INTEGER NULL,
            leave_type VARCHAR(80) NOT NULL DEFAULT 'Annual Leave',
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            days_requested NUMERIC(8,2) NOT NULL DEFAULT 0,
            reason TEXT NULL,
            status VARCHAR(40) NOT NULL DEFAULT 'pending',
            decision_note TEXT NULL,
            decided_by_user_id INTEGER NULL,
            decided_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NULL
        )
    '''))
    for stmt in [
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS applicant_user_id INTEGER",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS employee_user_id INTEGER NULL",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS franchise_user_id INTEGER NULL",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS manager_user_id INTEGER NULL",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS leave_type VARCHAR(80) NOT NULL DEFAULT 'Annual Leave'",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS start_date DATE",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS end_date DATE",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS days_requested NUMERIC(8,2) NOT NULL DEFAULT 0",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS reason TEXT NULL",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS status VARCHAR(40) NOT NULL DEFAULT 'pending'",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS decision_note TEXT NULL",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS decided_by_user_id INTEGER NULL",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS decided_at TIMESTAMP NULL",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()",
        "ALTER TABLE leave_applications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL",
    ]:
        db.execute(text(stmt))
    db.commit()


def _employee_profile(db: Session, user_id: int):
    return db.execute(text('''
        SELECT e.id AS employee_user_id, e.user_id, e.franchise_user_id, e.manager_user_id,
               e.name, e.surname, e.employee_role, e.email
        FROM employee_users e
        WHERE e.user_id = :uid AND COALESCE(e.is_active, TRUE) = TRUE
        LIMIT 1
    '''), {'uid': user_id}).mappings().first()


def _manager_profile(db: Session, user_id: int):
    return db.execute(text('''
        SELECT id AS manager_user_id, franchise_user_id FROM manager_users
        WHERE user_id = :uid AND COALESCE(is_active, TRUE) = TRUE
        LIMIT 1
    '''), {'uid': user_id}).mappings().first()


def _franchise_profile(db: Session, user_id: int):
    return db.execute(text('''
        SELECT id AS franchise_user_id FROM franchise_users
        WHERE user_id = :uid AND COALESCE(is_active, TRUE) = TRUE
        LIMIT 1
    '''), {'uid': user_id}).mappings().first()


def _calc_days(start_date: date, end_date: date) -> float:
    if end_date < start_date:
        raise HTTPException(status_code=400, detail='End date cannot be before start date')
    return float((end_date - start_date).days + 1)


def _franchise_notification_context(db: Session, franchise_user_id: int | None):
    if not franchise_user_id:
        return None
    row = db.execute(text('''
        SELECT fu.id AS franchise_user_id, fu.user_id AS recipient_user_id,
               u.email AS recipient_email,
               COALESCE(fu.franchise_name, u.full_name, u.email, 'Franchise') AS franchise_name
        FROM franchise_users fu
        JOIN users u ON u.id = fu.user_id
        WHERE fu.id = :fid
        LIMIT 1
    '''), {'fid': franchise_user_id}).mappings().first()
    return dict(row) if row else None


def _notify_franchise_leave_event(db: Session, application_id: int, notification_type: str, subject_prefix: str):
    app = db.execute(text('''
        SELECT la.*, COALESCE(e.name, m.name, u.full_name) AS name, COALESCE(e.surname, m.surname, '') AS surname,
               u.email AS applicant_email
        FROM leave_applications la
        JOIN users u ON u.id = la.applicant_user_id
        LEFT JOIN employee_users e ON e.user_id = la.applicant_user_id
        LEFT JOIN manager_users m ON m.user_id = la.applicant_user_id
        WHERE la.id = :id
        LIMIT 1
    '''), {'id': application_id}).mappings().first()
    if not app:
        return
    app = dict(app)
    ctx = _franchise_notification_context(db, app.get('franchise_user_id'))
    if not ctx:
        return
    staff_name = ' '.join(str(x or '').strip() for x in [app.get('name'), app.get('surname')] if str(x or '').strip()) or app.get('applicant_email') or f"User #{app.get('applicant_user_id')}"
    subject = f"{subject_prefix}: {staff_name}"
    message = (
        f"{staff_name} - {app.get('leave_type') or 'Leave'}\n"
        f"Dates: {format_sa_date(app.get('start_date'))} to {format_sa_date(app.get('end_date'))}\n"
        f"Status: {app.get('status')}\n"
        f"Reason: {app.get('reason') or 'n/a'}"
    )
    create_notification(
        db,
        notification_type=notification_type,
        subject=subject,
        message=message,
        recipient_email=ctx.get('recipient_email'),
        user_id=app.get('applicant_user_id'),
        recipient_user_id=ctx.get('recipient_user_id'),
        franchise_user_id=ctx.get('franchise_user_id'),
        related_table='leave_applications',
        related_id=int(application_id),
        severity='info' if app.get('status') == 'approved' else 'warning',
        target_tab='leave',
        send_email=True,
    )


class LeaveApplyRequest(BaseModel):
    leave_type: str = 'Annual Leave'
    start_date: date
    end_date: date
    reason: str | None = None


class LeaveDecisionRequest(BaseModel):
    note: str | None = None




@router.post('/apply')
def apply_leave(payload: LeaveApplyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tables(db)
    employee = _employee_profile(db, current_user.id)
    manager = _manager_profile(db, current_user.id)
    if not employee and not manager:
        raise HTTPException(status_code=403, detail='Only employees or managers can apply for leave')
    days = _calc_days(payload.start_date, payload.end_date)
    franchise_user_id = employee['franchise_user_id'] if employee else manager['franchise_user_id']
    manager_user_id = employee['manager_user_id'] if employee else None
    employee_user_id = employee['employee_user_id'] if employee else None
    app_id = db.execute(text('''
        INSERT INTO leave_applications (applicant_user_id, employee_user_id, franchise_user_id, manager_user_id,
            leave_type, start_date, end_date, days_requested, reason, status, created_at)
        VALUES (:applicant_user_id, :employee_user_id, :franchise_user_id, :manager_user_id,
            :leave_type, :start_date, :end_date, :days_requested, :reason, 'pending', :created_at)
        RETURNING id
    '''), {
        'applicant_user_id': current_user.id,
        'employee_user_id': employee_user_id,
        'franchise_user_id': franchise_user_id,
        'manager_user_id': manager_user_id,
        'leave_type': payload.leave_type,
        'start_date': payload.start_date,
        'end_date': payload.end_date,
        'days_requested': days,
        'reason': payload.reason,
        'created_at': now_sa_naive(),
    }).scalar_one()
    db.commit()
    _notify_franchise_leave_event(db, app_id, 'leave_application', 'Leave application submitted')
    return {'message': 'Leave application submitted', 'application_id': app_id, 'days_requested': days}


def _scope_where(db: Session, current_user: User):
    roles = _roles(db, current_user)
    if 'SuperUser' in roles:
        return '1=1', {}
    franchise = _franchise_profile(db, current_user.id)
    if franchise:
        return 'la.franchise_user_id = :fid', {'fid': franchise['franchise_user_id']}
    manager = _manager_profile(db, current_user.id)
    if manager:
        return '(la.applicant_user_id = :uid OR la.manager_user_id = :mid)', {'uid': current_user.id, 'mid': manager['manager_user_id']}
    return 'la.applicant_user_id = :uid', {'uid': current_user.id}


@router.get('/applications')
def list_leave_applications(status: str = '', current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_tables(db)
    where, params = _scope_where(db, current_user)
    # Hide leave records once their leave period has ended.
    where += ' AND la.end_date >= :today'
    params['today'] = now_sa_naive().date()
    params['current_uid'] = current_user.id
    if status:
        where += ' AND LOWER(la.status) = :status'
        params['status'] = status.lower()
    rows = db.execute(text(f'''
        SELECT la.*, u.full_name, u.email,
               COALESCE(e.name, m.name, u.full_name) AS name,
               COALESCE(e.surname, m.surname, '') AS surname,
               COALESCE(e.employee_role, CASE WHEN m.id IS NOT NULL THEN 'Manager' ELSE 'Employee' END) AS role,
               (la.end_date + INTERVAL '1 day')::date AS return_date
        FROM leave_applications la
        JOIN users u ON u.id = la.applicant_user_id AND COALESCE(u.is_active, TRUE) = TRUE
        LEFT JOIN employee_users e ON e.user_id = la.applicant_user_id AND COALESCE(e.is_active, TRUE) = TRUE
        LEFT JOIN manager_users m ON m.user_id = la.applicant_user_id AND COALESCE(m.is_active, TRUE) = TRUE
        WHERE {where}
          AND (e.id IS NOT NULL OR m.id IS NOT NULL OR la.applicant_user_id = :current_uid)
        ORDER BY la.start_date ASC, la.end_date ASC, la.created_at DESC
        LIMIT 500
    '''), params).mappings().all()
    return [dict(r) for r in rows]


def _can_decide(db: Session, current_user: User, app: dict) -> bool:
    roles = _roles(db, current_user)
    if int(app.get('applicant_user_id') or 0) == int(current_user.id):
        return False
    if 'SuperUser' in roles:
        return True
    franchise = _franchise_profile(db, current_user.id)
    if franchise and app.get('franchise_user_id') is not None and int(franchise['franchise_user_id']) == int(app['franchise_user_id']):
        return True
    manager = _manager_profile(db, current_user.id)
    if manager and app.get('manager_user_id') is not None and int(app['manager_user_id']) == int(manager['manager_user_id']):
        return True
    return False


def _decision(application_id: int, decision: str, payload: LeaveDecisionRequest, current_user: User, db: Session):
    _ensure_tables(db)
    app = db.execute(text('SELECT * FROM leave_applications WHERE id = :id'), {'id': application_id}).mappings().first()
    if not app:
        raise HTTPException(status_code=404, detail='Leave application not found')
    app = dict(app)
    if str(app['status']).lower() != 'pending':
        raise HTTPException(status_code=400, detail='Leave application was already decided')
    if not _can_decide(db, current_user, app):
        raise HTTPException(status_code=403, detail='You may not decide this leave application')
    now = now_sa_naive()
    db.execute(text('''
        UPDATE leave_applications
        SET status = :status,
            decision_note = :note,
            decided_by_user_id = :decider,
            decided_at = :now,
            updated_at = :now
        WHERE id = :id
    '''), {'status': decision, 'note': payload.note, 'decider': current_user.id, 'now': now, 'id': application_id})
    db.commit()
    _notify_franchise_leave_event(db, application_id, f'leave_{decision}', f'Leave application {decision}')
    return {'message': f'Leave application {decision}', 'application_id': application_id}


@router.post('/applications/{application_id}/approve')
def approve_leave(application_id: int, payload: LeaveDecisionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _decision(application_id, 'approved', payload, current_user, db)


@router.post('/applications/{application_id}/decline')
def decline_leave(application_id: int, payload: LeaveDecisionRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _decision(application_id, 'declined', payload, current_user, db)
