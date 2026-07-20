from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.core import User, UserRole
from app.services.notification_service import create_notification, ensure_notifications_schema
from app.services.email_service import get_email_config, send_smtp_email

router = APIRouter()

def now_sa_naive():
    return datetime.now(ZoneInfo("Africa/Johannesburg")).replace(tzinfo=None)

def _role_names(db: Session, user: User) -> list[str]:
    return [ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]


def _ensure_notification_table(db: Session):
    """Create or migrate notifications without requiring manual SQL."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NULL,
            recipient_user_id INTEGER NULL,
            franchise_user_id INTEGER NULL,
            recipient_email VARCHAR(255) NULL,
            recipient_number VARCHAR(80) NULL,
            notification_type VARCHAR(80) NOT NULL DEFAULT 'system',
            subject VARCHAR(255) NOT NULL DEFAULT 'Notification',
            message TEXT NOT NULL DEFAULT '',
            status VARCHAR(40) NOT NULL DEFAULT 'pending',
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            severity VARCHAR(40) NOT NULL DEFAULT 'info',
            target_tab VARCHAR(80) NULL,
            related_table VARCHAR(120) NULL,
            related_id INTEGER NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NULL
        )
    """))
    migrations = [
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_id INTEGER NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS recipient_user_id INTEGER NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS franchise_user_id INTEGER NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS recipient_email VARCHAR(255) NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS recipient_number VARCHAR(80) NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS notification_type VARCHAR(80) NOT NULL DEFAULT 'system'",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS subject VARCHAR(255) NOT NULL DEFAULT 'Notification'",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS message TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS status VARCHAR(40) NOT NULL DEFAULT 'pending'",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS is_read BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS severity VARCHAR(40) NOT NULL DEFAULT 'info'",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS target_tab VARCHAR(80) NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS related_table VARCHAR(120) NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS related_id INTEGER NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL",
    ]
    for stmt in migrations:
        db.execute(text(stmt))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_notifications_user_type_date
        ON notifications (user_id, notification_type, created_at DESC)
    """))
    db.commit()



def _cleanup_deleted_staff_notifications(db: Session):
    """Remove notifications that belong to deleted/inactive staff or deleted source records.

    This keeps the Overview latest notifications and the Outbox notifications from showing
    employees/managers after they have been removed from the system.
    """
    _ensure_notification_table(db)
    db.execute(text('''
        DELETE FROM notifications n
        WHERE (
            n.user_id IS NOT NULL
            AND (
                NOT EXISTS (
                    SELECT 1 FROM users u
                    WHERE u.id = n.user_id AND COALESCE(u.is_active, TRUE) = TRUE
                )
                OR EXISTS (
                    SELECT 1 FROM employee_users e
                    WHERE e.user_id = n.user_id AND COALESCE(e.is_active, TRUE) = FALSE
                )
                OR EXISTS (
                    SELECT 1 FROM manager_users m
                    WHERE m.user_id = n.user_id AND COALESCE(m.is_active, TRUE) = FALSE
                )
            )
        )
        OR (
            n.related_table = 'leave_applications'
            AND n.related_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM leave_applications la WHERE la.id = n.related_id)
        )
        OR (
            n.related_table = 'attendance_events'
            AND n.related_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM attendance_events ae WHERE ae.id = n.related_id)
        )
        OR (
            n.related_table = 'irp5_documents'
            AND n.related_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM irp5_documents doc WHERE doc.id = n.related_id)
        )
    '''))
    db.commit()

def _visible_staff(db: Session, current_user: User) -> list[dict]:
    roles = set(_role_names(db, current_user))
    if 'SuperUser' in roles:
        rows = db.execute(text('''
            SELECT u.id AS user_id, u.email AS login_email, COALESCE(u.is_active, TRUE) AS user_active,
                   COALESCE(e.name, m.name, u.full_name) AS name,
                   COALESCE(e.surname, m.surname, '') AS surname,
                   COALESCE(e.email, m.email, u.email) AS email,
                   COALESCE(e.contact_number, m.contact_number) AS contact_number,
                   COALESCE(e.office_address_assigned, m.office_address_assigned) AS office,
                   COALESCE(e.employee_role, CASE WHEN m.id IS NOT NULL THEN 'Manager' ELSE NULL END) AS role,
                   CASE WHEN e.id IS NOT NULL THEN 'Employee' WHEN m.id IS NOT NULL THEN 'Manager' ELSE 'User' END AS staff_type,
                   CONCAT(mm.name, ' ', mm.surname) AS manager_name,
                   COALESCE(e.is_active, m.is_active, u.is_active, TRUE) AS is_active
            FROM users u
            LEFT JOIN employee_users e ON e.user_id = u.id
            LEFT JOIN manager_users m ON m.user_id = u.id
            LEFT JOIN manager_users mm ON e.manager_user_id = mm.id
            WHERE COALESCE(e.id, m.id) IS NOT NULL
              AND COALESCE(u.is_active, TRUE) = TRUE
              AND COALESCE(e.is_active, m.is_active, TRUE) = TRUE
            ORDER BY name, surname
        ''')).mappings().all()
    elif 'FranchiseUser' in roles:
        franchise = db.execute(text('''
            SELECT id FROM franchise_users WHERE user_id = :uid AND COALESCE(is_active, TRUE) = TRUE LIMIT 1
        '''), {'uid': current_user.id}).mappings().first()
        if not franchise:
            raise HTTPException(status_code=403, detail='No active franchise profile found')
        rows = db.execute(text('''
            SELECT u.id AS user_id, u.email AS login_email, COALESCE(u.is_active, TRUE) AS user_active,
                   COALESCE(e.name, m.name, u.full_name) AS name,
                   COALESCE(e.surname, m.surname, '') AS surname,
                   COALESCE(e.email, m.email, u.email) AS email,
                   COALESCE(e.contact_number, m.contact_number) AS contact_number,
                   COALESCE(e.office_address_assigned, m.office_address_assigned) AS office,
                   COALESCE(e.employee_role, CASE WHEN m.id IS NOT NULL THEN 'Manager' ELSE NULL END) AS role,
                   CASE WHEN e.id IS NOT NULL THEN 'Employee' WHEN m.id IS NOT NULL THEN 'Manager' ELSE 'User' END AS staff_type,
                   CONCAT(mm.name, ' ', mm.surname) AS manager_name,
                   COALESCE(e.is_active, m.is_active, u.is_active, TRUE) AS is_active
            FROM users u
            LEFT JOIN employee_users e ON e.user_id = u.id AND e.franchise_user_id = :fid
            LEFT JOIN manager_users m ON m.user_id = u.id AND m.franchise_user_id = :fid
            LEFT JOIN manager_users mm ON e.manager_user_id = mm.id
            WHERE COALESCE(e.id, m.id) IS NOT NULL
              AND COALESCE(u.is_active, TRUE) = TRUE
              AND COALESCE(e.is_active, m.is_active, TRUE) = TRUE
            ORDER BY name, surname
        '''), {'fid': franchise['id']}).mappings().all()
    elif 'ManagerUser' in roles:
        manager = db.execute(text('''
            SELECT id, franchise_user_id FROM manager_users WHERE user_id = :uid AND COALESCE(is_active, TRUE) = TRUE LIMIT 1
        '''), {'uid': current_user.id}).mappings().first()
        if not manager:
            return []
        rows = db.execute(text('''
            SELECT u.id AS user_id, u.email AS login_email, COALESCE(u.is_active, TRUE) AS user_active,
                   COALESCE(e.name, u.full_name) AS name,
                   COALESCE(e.surname, '') AS surname,
                   COALESCE(e.email, u.email) AS email,
                   e.contact_number AS contact_number,
                   e.office_address_assigned AS office,
                   e.employee_role AS role,
                   'Employee' AS staff_type,
                   '' AS manager_name,
                   COALESCE(e.is_active, u.is_active, TRUE) AS is_active
            FROM employee_users e
            JOIN users u ON u.id = e.user_id
            WHERE COALESCE(e.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE
              AND e.manager_user_id = :mid
            ORDER BY e.name, e.surname
        '''), {'mid': manager['id']}).mappings().all()
    else:
        rows = db.execute(text('''
            SELECT id AS user_id, email AS login_email, full_name AS name, '' AS surname, email, NULL AS contact_number,
                   NULL AS office, NULL AS role, 'User' AS staff_type, '' AS manager_name, COALESCE(is_active, TRUE) AS is_active
            FROM users WHERE id = :uid
        '''), {'uid': current_user.id}).mappings().all()

    cleaned = []
    for r in rows:
        d = dict(r)
        if d.get('is_active') is False:
            continue
        full_name = ' '.join(str(x or '').strip() for x in [d.get('name'), d.get('surname')] if str(x or '').strip()).strip()
        d['full_name'] = full_name or f"User #{d['user_id']}"
        cleaned.append(d)
    return cleaned


def _today_bounds():
    start = datetime.combine(date.today(), datetime.min.time())
    end = start + timedelta(days=1)
    return start, end


def _event_rows_for_users(db: Session, user_ids: list[int]):
    ids = [int(x) for x in user_ids if x is not None]
    if not ids:
        return []
    start, end = _today_bounds()
    placeholders = ', '.join(f':uid_{i}' for i in range(len(ids)))
    params = {f'uid_{i}': uid for i, uid in enumerate(ids)}
    params.update({'start': start, 'end': end})
    return db.execute(text(f'''
        SELECT id, user_id, action, created_at, gps_status, is_late, late_minutes,
               left_early, early_leave_minutes, missing_sign_out
        FROM attendance_events
        WHERE user_id IN ({placeholders})
          AND created_at >= :start
          AND created_at < :end
        ORDER BY created_at ASC
    '''), params).mappings().all()


def _status_item(staff, status_code, status_label):
    return {
        'user_id': staff['user_id'],
        'full_name': staff['full_name'],
        'email': staff.get('email'),
        'contact_number': staff.get('contact_number'),
        'role': staff.get('role'),
        'staff_type': staff.get('staff_type'),
        'manager_name': staff.get('manager_name'),
        'office': staff.get('office'),
        'status_code': status_code,
        'status_label': status_label,
    }


def _upsert_system_notification(db: Session, current_user: User, notification_type: str, subject: str, message: str, related_id: int | None = None, severity: str = 'info', target_tab: str | None = None, related_table: str = 'attendance_events'):
    _ensure_notification_table(db)
    today_start = datetime.combine(date.today(), datetime.min.time())
    existing = db.execute(text("""
        SELECT id FROM notifications
        WHERE (user_id = :user_id OR user_id IS NULL)
          AND notification_type = :notification_type
          AND subject = :subject
          AND created_at >= :today
        LIMIT 1
    """), {'user_id': current_user.id, 'notification_type': notification_type, 'subject': subject, 'today': today_start}).mappings().first()
    params = {
        'user_id': current_user.id,
        'notification_type': notification_type,
        'subject': subject,
        'message': message,
        'severity': severity,
        'target_tab': target_tab,
        'related_table': related_table,
        'related_id': related_id,
        'now': datetime.utcnow(),
    }
    if existing:
        db.execute(text("""
            UPDATE notifications
            SET message = :message, severity = :severity, target_tab = :target_tab,
                related_table = :related_table, related_id = :related_id, updated_at = :now
            WHERE id = :id
        """), {**params, 'id': existing['id']})
    else:
        db.execute(text("""
            INSERT INTO notifications (user_id, notification_type, subject, message, status, is_read, severity, target_tab, related_table, related_id, created_at)
            VALUES (:user_id, :notification_type, :subject, :message, 'pending', FALSE, :severity, :target_tab, :related_table, :related_id, :now)
        """), params)
    db.commit()

def _ensure_leave_table(db: Session):
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
    db.commit()


def _leave_scope_where(db: Session, current_user: User):
    role_set = set(_role_names(db, current_user))
    base_where = '1=1'
    params = {'today': date.today(), 'current_uid': current_user.id}
    if 'SuperUser' in role_set:
        return base_where, params
    if 'FranchiseUser' in role_set:
        franchise = db.execute(text('''
            SELECT id FROM franchise_users WHERE user_id = :uid AND COALESCE(is_active, TRUE) = TRUE LIMIT 1
        '''), {'uid': current_user.id}).mappings().first()
        if franchise:
            base_where += ' AND la.franchise_user_id = :fid'
            params['fid'] = franchise['id']
        else:
            base_where += ' AND la.applicant_user_id = :uid'
            params['uid'] = current_user.id
        return base_where, params
    if 'ManagerUser' in role_set:
        manager = db.execute(text('''
            SELECT id, franchise_user_id FROM manager_users WHERE user_id = :uid AND COALESCE(is_active, TRUE) = TRUE LIMIT 1
        '''), {'uid': current_user.id}).mappings().first()
        if manager:
            base_where += ' AND (la.manager_user_id = :mid OR la.franchise_user_id = :fid OR la.applicant_user_id = :uid)'
            params['mid'] = manager['id']
            params['fid'] = manager['franchise_user_id']
            params['uid'] = current_user.id
        else:
            base_where += ' AND la.applicant_user_id = :uid'
            params['uid'] = current_user.id
        return base_where, params
    base_where += ' AND la.applicant_user_id = :uid'
    params['uid'] = current_user.id
    return base_where, params


def _leave_rows(db: Session, current_user: User):
    _ensure_leave_table(db)
    base_where, params = _leave_scope_where(db, current_user)
    rows = db.execute(text(f'''
        SELECT la.id, la.applicant_user_id AS user_id, la.leave_type, la.start_date, la.end_date,
               la.days_requested, la.reason, COALESCE(LOWER(la.status), 'pending') AS status,
               COALESCE(e.name, m.name, u.full_name) AS name,
               COALESCE(e.surname, m.surname, '') AS surname,
               COALESCE(e.email, m.email, u.email) AS email,
               COALESCE(e.employee_role, CASE WHEN m.id IS NOT NULL THEN 'Manager' ELSE 'Employee' END) AS role
        FROM leave_applications la
        JOIN users u ON u.id = la.applicant_user_id AND COALESCE(u.is_active, TRUE) = TRUE
        LEFT JOIN employee_users e ON e.user_id = la.applicant_user_id AND COALESCE(e.is_active, TRUE) = TRUE
        LEFT JOIN manager_users m ON m.user_id = la.applicant_user_id AND COALESCE(m.is_active, TRUE) = TRUE
        WHERE {base_where}
          AND (e.id IS NOT NULL OR m.id IS NOT NULL OR la.applicant_user_id = :current_uid)
        ORDER BY la.start_date ASC, la.end_date ASC, la.created_at DESC
        LIMIT 250
    '''), params).mappings().all()
    return [dict(r) for r in rows]


def _format_leave(r: dict):
    end_date = r.get('end_date')
    try:
        return_date = str(end_date + timedelta(days=1)) if end_date else ''
    except Exception:
        return_date = str(end_date or '')
    status = str(r.get('status') or 'pending').lower()
    full_name = ' '.join(str(x or '').strip() for x in [r.get('name'), r.get('surname')] if str(x or '').strip()) or f"User #{r['user_id']}"
    return {
        'application_id': int(r['id']),
        'user_id': int(r['user_id']),
        'full_name': full_name,
        'email': r.get('email'),
        'role': r.get('role'),
        'staff_type': 'Leave',
        'manager_name': '',
        'office': f"{r.get('start_date')} to {r.get('end_date')}",
        'leave_type': r.get('leave_type') or 'Leave',
        'leave_start': str(r.get('start_date')),
        'leave_end': str(r.get('end_date')),
        'return_date': return_date,
        'reason': r.get('reason') or 'No reason supplied',
        'status_code': status,
        'status_label': status.title(),
    }


@router.get('/summary')
def alerts_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_notification_table(db)
    _cleanup_deleted_staff_notifications(db)
    staff = _visible_staff(db, current_user)
    user_ids = [int(s['user_id']) for s in staff]
    events = list(_event_rows_for_users(db, user_ids))
    by_user: dict[int, list[dict]] = {}
    for event in events:
        by_user.setdefault(int(event['user_id']), []).append(dict(event))

    lists = {'not_signed_in': [], 'late': [], 'missing_sign_out': [], 'gps_issues': [], 'pending_leave': [], 'approved_leave': [], 'leave_applications': []}
    completed = 0
    for person in staff:
        uid = int(person['user_id'])
        person_events = by_user.get(uid, [])
        sign_ins = [e for e in person_events if e['action'] == 'sign_in']
        sign_outs = [e for e in person_events if e['action'] == 'sign_out']
        latest = person_events[-1] if person_events else None
        if not sign_ins:
            lists['not_signed_in'].append(_status_item(person, 'not_signed_in', 'Not signed in'))
        if any(bool(e.get('is_late')) for e in sign_ins):
            lists['late'].append(_status_item(person, 'late', 'Late'))
        if sign_ins and (not sign_outs or (latest and latest.get('action') == 'sign_in')):
            lists['missing_sign_out'].append(_status_item(person, 'missing_sign_out', 'Missing sign-out'))
        if any(e.get('gps_status') in ('outside_area', 'accuracy_too_low', 'no_allocation') for e in person_events):
            status = next((e.get('gps_status') for e in person_events if e.get('gps_status') in ('outside_area', 'accuracy_too_low', 'no_allocation')), 'gps_issue')
            lists['gps_issues'].append(_status_item(person, status, status.replace('_', ' ').title()))
        if sign_ins and sign_outs:
            completed += 1

    try:
        leave_rows = _leave_rows(db, current_user)
    except Exception:
        leave_rows = []

    today = now_sa_naive().date()
    formatted_leave = [_format_leave(r) for r in leave_rows if r.get('end_date') and r.get('end_date') >= today]
    lists['leave_applications'] = formatted_leave
    lists['pending_leave'] = [x for x in formatted_leave if x['status_code'] == 'pending']
    lists['approved_leave'] = [x for x in formatted_leave if x['status_code'] == 'approved' and x.get('leave_end') and x.get('leave_end') >= str(today)]

    metrics = {
        'total_staff': len(staff),
        'not_signed_in': len(lists['not_signed_in']),
        'late': len(lists['late']),
        'missing_sign_out': len(lists['missing_sign_out']),
        'outside_area': len([i for i in lists['gps_issues'] if i['status_code'] == 'outside_area']),
        'low_accuracy': len([i for i in lists['gps_issues'] if i['status_code'] == 'accuracy_too_low']),
        'completed': completed,
        'pending_leave': len(lists['pending_leave']),
        'approved_leave': len(lists['approved_leave']),
    }

    suggestions = []
    if metrics['not_signed_in']:
        suggestions.append({'level': 'warning', 'title': 'Absent / not signed in today', 'message': f"{metrics['not_signed_in']} active staff member(s) have not signed in today.", 'action': 'Open History and contact each staff member or their manager.', 'target_tab': 'history'})
        _upsert_system_notification(db, current_user, 'not_signed_in', 'Staff not signed in', f"{metrics['not_signed_in']} active staff member(s) have not signed in today.", severity='warning', target_tab='history')
    if metrics['late']:
        suggestions.append({'level': 'warning', 'title': 'Late arrivals require review', 'message': f"{metrics['late']} staff member(s) were late today.", 'action': 'Open Approvals to review late arrivals and add manager notes.', 'target_tab': 'approvals'})
        _upsert_system_notification(db, current_user, 'late', 'Late arrivals', f"{metrics['late']} staff member(s) were late today.", severity='warning', target_tab='approvals')
    if metrics['missing_sign_out']:
        suggestions.append({'level': 'danger', 'title': 'Missing sign-outs', 'message': f"{metrics['missing_sign_out']} staff member(s) have open sessions.", 'action': 'Open Approvals before payroll cut-off.', 'target_tab': 'approvals'})
        _upsert_system_notification(db, current_user, 'missing_sign_out', 'Missing sign-outs', f"{metrics['missing_sign_out']} staff member(s) have open attendance sessions.", severity='danger', target_tab='approvals')
    if metrics['outside_area'] or metrics['low_accuracy']:
        suggestions.append({'level': 'danger', 'title': 'GPS exception found', 'message': 'Some attendance records are outside the assigned area or have low GPS accuracy.', 'action': 'Open Approvals and verify office allocation, radius, and device location permissions.', 'target_tab': 'approvals'})
        _upsert_system_notification(db, current_user, 'gps_issue', 'GPS attendance exception', 'Some attendance records are outside assigned area or have low GPS accuracy.', severity='danger', target_tab='approvals')
    if metrics.get('pending_leave'):
        suggestions.append({'level': 'info', 'title': 'Leave applications pending', 'message': f"{metrics['pending_leave']} leave application(s) need review.", 'action': 'Open Leave to approve or decline applications.', 'target_tab': 'leave'})
        _upsert_system_notification(db, current_user, 'leave_pending', 'Pending leave applications', f"{metrics['pending_leave']} leave application(s) need review.", severity='info', target_tab='leave', related_table='leave_applications')
    if metrics.get('approved_leave'):
        names = ', '.join([x.get('full_name', 'Staff') for x in lists['approved_leave'][:3]])
        suggestions.append({'level': 'info', 'title': 'Staff on approved leave', 'message': f"{metrics['approved_leave']} staff member(s) have approved current or upcoming leave. {names}", 'action': 'Check return dates and arrange cover where needed.', 'target_tab': 'leave'})
        _upsert_system_notification(db, current_user, 'leave_approved', 'Staff on approved leave', f"{metrics['approved_leave']} staff member(s) have approved leave scheduled.", severity='info', target_tab='leave', related_table='leave_applications')
    if metrics['not_signed_in'] >= 3:
        suggestions.append({'level': 'warning', 'title': 'Create a morning follow-up routine', 'message': 'Several staff have not signed in. A reminder after shift start can reduce missed attendance records.', 'action': 'Review the Not signed in today block and contact line managers.', 'target_tab': 'history'})
    if metrics['late'] >= 2:
        suggestions.append({'level': 'warning', 'title': 'Check recurring late patterns', 'message': 'More than one staff member is late. Compare this with office hours and transport patterns.', 'action': 'Use History to filter by each staff member.', 'target_tab': 'history'})
    if metrics['missing_sign_out']:
        suggestions.append({'level': 'danger', 'title': 'Protect payroll accuracy', 'message': 'Missing sign-outs can affect total hours and payroll calculations.', 'action': 'Resolve open sessions before running payroll.', 'target_tab': 'approvals'})
    if not suggestions:
        suggestions.append({'level': 'success', 'title': 'Attendance looks stable', 'message': 'No urgent exceptions were found for your current scope.', 'action': 'Keep monitoring throughout the day.', 'target_tab': 'overview'})

    notifications = db.execute(text('''
        SELECT id, user_id, recipient_user_id, franchise_user_id, notification_type, subject, message, status, is_read, severity, target_tab, related_table, related_id, created_at
        FROM notifications
        WHERE (user_id = :user_id OR recipient_user_id = :user_id OR (user_id IS NULL AND recipient_user_id IS NULL))
          AND (
              user_id IS NULL
              OR EXISTS (SELECT 1 FROM users u WHERE u.id = notifications.user_id AND COALESCE(u.is_active, TRUE) = TRUE)
          )
        ORDER BY created_at DESC
        LIMIT 20
    '''), {'user_id': current_user.id}).mappings().all()

    return {'metrics': metrics, 'lists': lists, 'suggestions': suggestions, 'notifications': [dict(n) for n in notifications]}


@router.get('/notifications')
def list_notifications(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_notification_table(db)
    _cleanup_deleted_staff_notifications(db)
    rows = db.execute(text('''
        SELECT id, user_id, recipient_user_id, franchise_user_id, notification_type, subject, message, status, is_read, severity, target_tab, related_table, related_id, created_at
        FROM notifications
        WHERE (user_id = :user_id OR recipient_user_id = :user_id OR (user_id IS NULL AND recipient_user_id IS NULL))
          AND (
              user_id IS NULL
              OR EXISTS (SELECT 1 FROM users u WHERE u.id = notifications.user_id AND COALESCE(u.is_active, TRUE) = TRUE)
          )
        ORDER BY created_at DESC
        LIMIT 100
    '''), {'user_id': current_user.id}).mappings().all()
    return [dict(r) for r in rows]


class ManualNotificationRequest(BaseModel):
    subject: str
    message: str
    notification_type: str = 'manual'


@router.post('/notifications')
def create_manual_notification(payload: ManualNotificationRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_notification_table(db)
    db.execute(text('''
        INSERT INTO notifications (user_id, notification_type, subject, message, status, is_read, created_at)
        VALUES (:user_id, :notification_type, :subject, :message, 'pending', FALSE, :created_at)
    '''), {'user_id': current_user.id, 'notification_type': payload.notification_type, 'subject': payload.subject, 'message': payload.message, 'created_at': datetime.utcnow()})
    db.commit()
    return {'success': True}


@router.post('/notifications/{notification_id}/read')
def mark_read(notification_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_notification_table(db)
    db.execute(text('''
        UPDATE notifications
        SET is_read = TRUE, status = 'read', updated_at = :updated_at
        WHERE id = :id
          AND (user_id = :user_id OR recipient_user_id = :user_id OR (user_id IS NULL AND recipient_user_id IS NULL))
    '''), {'id': notification_id, 'user_id': current_user.id, 'updated_at': datetime.utcnow()})
    db.commit()
    return {'success': True}


class EmailTestRequest(BaseModel):
    recipient_email: str | None = None


@router.get('/email-config')
def email_config(current_user: User = Depends(get_current_user)):
    # Safe SMTP diagnostics. Password is never returned.
    return get_email_config().safe_dict()


@router.post('/email-test')
def send_email_test(payload: EmailTestRequest | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Send a real SMTP test email and store the result in the notification outbox.
    recipient = payload.recipient_email if payload and payload.recipient_email else current_user.email
    subject = 'Attendance Register Platform email test'
    message = 'This is a test email from the Attendance Register Platform. If you received it, SMTP is working.'
    status_value, sent_at, error_message, diagnostics = send_smtp_email(recipient, subject, message)
    ensure_notifications_schema(db)
    row = db.execute(text("""
        INSERT INTO notifications (
            user_id, recipient_user_id, recipient_email, notification_type, subject, message,
            status, is_read, severity, target_tab, sent_at, error_message, created_at, updated_at
        ) VALUES (
            :user_id, :recipient_user_id, :recipient_email, 'email_test', :subject, :message,
            :status, FALSE, 'info', 'home', :sent_at, :error_message, :created_at, :updated_at
        ) RETURNING id
    """), {
        'user_id': current_user.id,
        'recipient_user_id': current_user.id,
        'recipient_email': recipient,
        'subject': subject,
        'message': message,
        'status': status_value,
        'sent_at': sent_at,
        'error_message': error_message,
        'created_at': datetime.utcnow(),
        'updated_at': now_sa_naive(),
    }).mappings().first()
    db.commit()
    return {
        'id': row['id'] if row else None,
        'recipient_email': recipient,
        'status': status_value,
        'sent_at': sent_at,
        'error_message': error_message,
        'smtp': diagnostics,
    }


@router.post('/email-retry-pending')
def retry_pending_emails(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Retry latest pending or failed email notifications that have a recipient email.
    ensure_notifications_schema(db)
    rows = db.execute(text("""
        SELECT id, recipient_email, subject, message
        FROM notifications
        WHERE recipient_email IS NOT NULL
          AND status IN ('pending', 'failed')
        ORDER BY created_at DESC
        LIMIT 25
    """)).mappings().all()
    results = []
    for r in rows:
        status_value, sent_at, error_message, diagnostics = send_smtp_email(r['recipient_email'], r['subject'], r['message'])
        db.execute(text("""
            UPDATE notifications
            SET status = :status, sent_at = :sent_at, error_message = :error_message, updated_at = :updated_at
            WHERE id = :id
        """), {
            'id': r['id'],
            'status': status_value,
            'sent_at': sent_at,
            'error_message': error_message,
            'updated_at': now_sa_naive(),
        })
        results.append({'id': r['id'], 'recipient_email': r['recipient_email'], 'status': status_value, 'error_message': error_message})
    db.commit()
    return {'count': len(results), 'results': results, 'smtp': get_email_config().safe_dict()}
