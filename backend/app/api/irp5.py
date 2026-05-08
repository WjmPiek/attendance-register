
from datetime import datetime
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.core import User, UserRole

router = APIRouter()
UPLOAD_DIR = Path(__file__).resolve().parents[2] / 'uploads' / 'irp5'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _roles(db: Session, user: User) -> list[str]:
    return [ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]


def _ensure_table(db: Session):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS irp5_documents (
            id SERIAL PRIMARY KEY,
            employee_user_id INTEGER NULL,
            target_user_id INTEGER NOT NULL,
            uploaded_by_user_id INTEGER NOT NULL,
            franchise_user_id INTEGER NULL,
            manager_user_id INTEGER NULL,
            original_filename VARCHAR(255) NOT NULL,
            stored_filename VARCHAR(255) NOT NULL,
            content_type VARCHAR(120) NULL,
            file_size INTEGER NULL,
            tax_year VARCHAR(20) NULL,
            notes TEXT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NULL
        )
    """))
    for stmt in [
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS employee_user_id INTEGER NULL",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS target_user_id INTEGER NULL",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS uploaded_by_user_id INTEGER NULL",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS franchise_user_id INTEGER NULL",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS manager_user_id INTEGER NULL",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255) NULL",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS stored_filename VARCHAR(255) NULL",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS content_type VARCHAR(120) NULL",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS file_size INTEGER NULL",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS tax_year VARCHAR(20) NULL",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS notes TEXT NULL",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS document_type VARCHAR(40) NULL DEFAULT 'IRP5'",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS target_staff_type VARCHAR(40) NULL DEFAULT 'employee'",
        "ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS target_staff_id INTEGER NULL",
    ]:
        db.execute(text(stmt))
    db.commit()
    try:
        db.execute(text("ALTER TABLE irp5_documents ALTER COLUMN employee_user_id DROP NOT NULL"))
        db.execute(text("ALTER TABLE irp5_documents ALTER COLUMN target_user_id DROP NOT NULL"))
    except Exception:
        db.rollback()
    else:
        db.commit()
    db.commit()


def _employee_row(db: Session, employee_id: int):
    row = db.execute(text("""
        SELECT eu.id AS employee_user_id, eu.user_id AS target_user_id, eu.franchise_user_id,
               eu.name, eu.surname, eu.employee_role, eu.manager_user_id, u.full_name, u.email
        FROM employee_users eu
        JOIN users u ON u.id = eu.user_id
        WHERE eu.id = :employee_id AND COALESCE(eu.is_active, TRUE) = TRUE
    """), {'employee_id': employee_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail='Employee not found')
    return dict(row)



def _manager_row(db: Session, manager_id: int):
    row = db.execute(text("""
        SELECT mu.id AS manager_user_id, mu.user_id AS target_user_id, mu.franchise_user_id,
               mu.name, mu.surname, u.full_name, u.email
        FROM manager_users mu
        JOIN users u ON u.id = mu.user_id
        WHERE mu.id = :manager_id AND COALESCE(mu.is_active, TRUE) = TRUE
    """), {'manager_id': manager_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail='Manager not found')
    return dict(row)

def _current_finance_employee(db: Session, current_user: User):
    return db.execute(text("""
        SELECT id, franchise_user_id, employee_role
        FROM employee_users
        WHERE user_id = :uid AND COALESCE(is_active, TRUE) = TRUE
        LIMIT 1
    """), {'uid': current_user.id}).mappings().first()


def _can_upload_for(db: Session, current_user: User, employee: dict) -> bool:
    roles = set(_roles(db, current_user))
    if 'SuperUser' in roles:
        return True
    if 'FranchiseUser' in roles:
        franchise = db.execute(text("""
            SELECT id FROM franchise_users
            WHERE user_id = :uid AND COALESCE(is_active, TRUE) = TRUE
            LIMIT 1
        """), {'uid': current_user.id}).mappings().first()
        return bool(franchise and int(franchise['id']) == int(employee['franchise_user_id']))
    finance = _current_finance_employee(db, current_user)
    if finance and 'finance' in (finance.get('employee_role') or '').strip().lower():
        return int(finance['franchise_user_id']) == int(employee['franchise_user_id'])
    return False


def _safe_name(filename: str) -> str:
    name = Path(filename or 'document.pdf').name.replace(' ', '_')
    return ''.join(ch for ch in name if ch.isalnum() or ch in '._-') or 'document.pdf'


def _document_scope_filter(db: Session, current_user: User, alias: str = 'd'):
    # Privacy rule: IRP5 files are personal tax documents. No role may list,
    # view, or download another user's IRP5 from the document endpoints.
    # Admin/franchise/finance users may upload/manage records via the upload
    # workflow, but downloads are limited to the linked user account.
    return f'{alias}.target_user_id = :uid', {'uid': current_user.id}




def _document_management_filter(db: Session, current_user: User, alias: str = 'd'):
    roles = set(_roles(db, current_user))
    if 'SuperUser' in roles:
        return '1=1', {}
    if 'FranchiseUser' in roles:
        franchise = db.execute(text('SELECT id FROM franchise_users WHERE user_id = :uid AND COALESCE(is_active, TRUE) = TRUE LIMIT 1'), {'uid': current_user.id}).mappings().first()
        if franchise:
            return f'{alias}.franchise_user_id = :fid', {'fid': franchise['id']}
    finance = _current_finance_employee(db, current_user)
    if finance and 'finance' in (finance.get('employee_role') or '').strip().lower():
        return f'{alias}.franchise_user_id = :fid', {'fid': finance['franchise_user_id']}
    return '1=0', {}


def _get_manageable_document(db: Session, current_user: User, document_id: int):
    where, params = _document_management_filter(db, current_user, 'd')
    params['id'] = document_id
    row = db.execute(text(f"""
        SELECT d.id
        FROM irp5_documents d
        WHERE d.id = :id
          AND COALESCE(d.is_active, TRUE) = TRUE
          AND {where}
        LIMIT 1
    """), params).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail='Document not found')
    return row

def _get_scoped_document(db: Session, current_user: User, document_id: int):
    where, params = _document_scope_filter(db, current_user, 'd')
    params['id'] = document_id
    row = db.execute(text(f"""
        SELECT d.*
        FROM irp5_documents d
        WHERE d.id = :id
          AND COALESCE(d.is_active, TRUE) = TRUE
          AND {where}
        LIMIT 1
    """), params).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail='Document not found')
    return row



@router.get('/employees')
def visible_employees_for_irp5(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles = set(_roles(db, current_user))
    params = {}
    where = 'COALESCE(eu.is_active, TRUE) = TRUE'
    if 'SuperUser' in roles:
        pass
    elif 'FranchiseUser' in roles:
        franchise = db.execute(text('SELECT id FROM franchise_users WHERE user_id = :uid LIMIT 1'), {'uid': current_user.id}).mappings().first()
        if not franchise:
            raise HTTPException(status_code=403, detail='No franchise profile found')
        where += ' AND eu.franchise_user_id = :fid'
        params['fid'] = franchise['id']
    else:
        finance = _current_finance_employee(db, current_user)
        if not finance or 'finance' not in (finance.get('employee_role') or '').strip().lower():
            raise HTTPException(status_code=403, detail='Only FranchiseUser, SuperUser or Finance employees can upload IRP5 documents')
        where += ' AND eu.franchise_user_id = :fid'
        params['fid'] = finance['franchise_user_id']
    rows = db.execute(text(f"""
        WITH staff AS (
            SELECT eu.id AS staff_id, eu.id AS employee_user_id, eu.user_id, eu.name, eu.surname,
                   eu.employee_role AS staff_role, eu.employee_role, eu.email, eu.contact_number,
                   eu.franchise_user_id, 'employee' AS staff_type
            FROM employee_users eu
            JOIN users u ON u.id = eu.user_id
            WHERE {where} AND COALESCE(u.is_active, TRUE) = TRUE
            UNION ALL
            SELECT mu.id AS staff_id, NULL AS employee_user_id, mu.user_id, mu.name, mu.surname,
                   'Manager' AS staff_role, 'Manager' AS employee_role, mu.email, mu.contact_number,
                   mu.franchise_user_id, 'manager' AS staff_type
            FROM manager_users mu
            JOIN users u ON u.id = mu.user_id
            WHERE COALESCE(mu.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE
              {'' if 'SuperUser' in roles else 'AND mu.franchise_user_id = :fid'}
        )
        SELECT * FROM staff
        ORDER BY name, surname
    """), params).mappings().all()
    return [dict(r) for r in rows]


@router.post('/employees/{employee_id}/upload')
def upload_irp5(employee_id: int, tax_year: str = '', notes: str = '', file: UploadFile = File(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_table(db)
    employee = _employee_row(db, employee_id)
    if not _can_upload_for(db, current_user, employee):
        raise HTTPException(status_code=403, detail='You may only upload IRP5 documents for employees in your allowed franchise scope')
    safe = _safe_name(file.filename)
    ext = Path(safe).suffix.lower()
    if ext not in {'.pdf', '.png', '.jpg', '.jpeg'}:
        raise HTTPException(status_code=400, detail='Only PDF, PNG or JPG files are allowed')
    stored = f'{employee_id}_{uuid.uuid4().hex}{ext}'
    dest = UPLOAD_DIR / stored
    size = 0
    with dest.open('wb') as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > 15 * 1024 * 1024:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail='File is too large. Maximum is 15 MB')
            out.write(chunk)
    doc_id = db.execute(text("""
        INSERT INTO irp5_documents (employee_user_id, target_user_id, uploaded_by_user_id, franchise_user_id, manager_user_id,
            original_filename, stored_filename, content_type, file_size, tax_year, notes, document_type, target_staff_type, target_staff_id, is_active, created_at)
        VALUES (:employee_user_id, :target_user_id, :uploaded_by_user_id, :franchise_user_id, :manager_user_id,
            :original_filename, :stored_filename, :content_type, :file_size, :tax_year, :notes, 'IRP5', 'employee', :employee_user_id, TRUE, :created_at)
        RETURNING id
    """), {
        'employee_user_id': employee['employee_user_id'], 'target_user_id': employee['target_user_id'],
        'uploaded_by_user_id': current_user.id, 'franchise_user_id': employee['franchise_user_id'], 'manager_user_id': employee.get('manager_user_id'),
        'original_filename': safe, 'stored_filename': stored, 'content_type': file.content_type,
        'file_size': size, 'tax_year': tax_year or None, 'notes': notes or None, 'created_at': datetime.utcnow(),
    }).scalar_one()
    db.commit()
    return {'message': 'IRP5 document uploaded', 'document_id': doc_id}


@router.post('/managers/{manager_id}/upload')
def upload_manager_irp5(manager_id: int, tax_year: str = '', notes: str = '', file: UploadFile = File(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_table(db)
    manager = _manager_row(db, manager_id)
    if not _can_upload_for(db, current_user, manager):
        raise HTTPException(status_code=403, detail='You may only upload IRP5 documents for managers in your allowed franchise scope')
    safe = _safe_name(file.filename)
    ext = Path(safe).suffix.lower()
    if ext not in {'.pdf', '.png', '.jpg', '.jpeg'}:
        raise HTTPException(status_code=400, detail='Only PDF, PNG or JPG files are allowed')
    stored = f'manager_{manager_id}_{uuid.uuid4().hex}{ext}'
    dest = UPLOAD_DIR / stored
    size = 0
    with dest.open('wb') as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > 15 * 1024 * 1024:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail='File is too large. Maximum is 15 MB')
            out.write(chunk)
    doc_id = db.execute(text("""
        INSERT INTO irp5_documents (employee_user_id, target_user_id, uploaded_by_user_id, franchise_user_id, manager_user_id,
            original_filename, stored_filename, content_type, file_size, tax_year, notes, document_type, target_staff_type, target_staff_id, is_active, created_at)
        VALUES (NULL, :target_user_id, :uploaded_by_user_id, :franchise_user_id, :manager_user_id,
            :original_filename, :stored_filename, :content_type, :file_size, :tax_year, :notes, 'IRP5', 'manager', :target_staff_id, TRUE, :created_at)
        RETURNING id
    """), {
        'target_user_id': manager['target_user_id'], 'uploaded_by_user_id': current_user.id,
        'franchise_user_id': manager['franchise_user_id'], 'manager_user_id': manager['manager_user_id'],
        'target_staff_id': manager['manager_user_id'], 'original_filename': safe, 'stored_filename': stored,
        'content_type': file.content_type, 'file_size': size, 'tax_year': tax_year or None,
        'notes': notes or None, 'created_at': datetime.utcnow(),
    }).scalar_one()
    db.commit()
    return {'message': 'Manager IRP5 document uploaded', 'document_id': doc_id}


@router.get('/documents')
def scoped_irp5_documents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_table(db)
    where, params = _document_scope_filter(db, current_user, 'd')
    rows = db.execute(text(f"""
        SELECT d.id, d.original_filename, d.content_type, d.file_size, d.tax_year, d.notes, d.created_at,
               d.target_user_id, d.franchise_user_id, d.target_staff_type, d.target_staff_id,
               COALESCE(e.name || ' ' || e.surname, m.name || ' ' || m.surname, u.full_name, u.email) AS staff_name
        FROM irp5_documents d
        LEFT JOIN users u ON u.id = d.target_user_id
        LEFT JOIN employee_users e ON (d.target_staff_type = 'employee' AND e.id = d.target_staff_id) OR (d.target_staff_type IS NULL AND e.user_id = d.target_user_id)
        LEFT JOIN manager_users m ON (d.target_staff_type = 'manager' AND m.id = d.target_staff_id) OR (d.target_staff_type IS NULL AND m.user_id = d.target_user_id)
        WHERE COALESCE(d.is_active, TRUE) = TRUE AND {where}
        ORDER BY d.created_at DESC
        LIMIT 500
    """), params).mappings().all()
    return [dict(r) for r in rows]


@router.get('/my-documents')
def my_irp5_documents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_table(db)
    rows = db.execute(text("""
        SELECT id, original_filename, content_type, file_size, tax_year, notes, created_at
        FROM irp5_documents
        WHERE target_user_id = :uid AND COALESCE(is_active, TRUE) = TRUE
        ORDER BY created_at DESC
    """), {'uid': current_user.id}).mappings().all()
    return [dict(r) for r in rows]


@router.get('/documents/{document_id}/download')
def download_irp5(document_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_table(db)
    row = _get_scoped_document(db, current_user, document_id)
    path = UPLOAD_DIR / row['stored_filename']
    if not path.exists():
        raise HTTPException(status_code=404, detail='Stored document file is missing')
    return FileResponse(path, media_type=row.get('content_type') or 'application/octet-stream', filename=row['original_filename'])


@router.delete('/documents/{document_id}')
def delete_irp5_document(document_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_table(db)
    roles = set(_roles(db, current_user))
    finance = _current_finance_employee(db, current_user)
    can_delete = 'SuperUser' in roles or 'FranchiseUser' in roles or bool(finance and 'finance' in (finance.get('employee_role') or '').strip().lower())
    if not can_delete:
        raise HTTPException(status_code=403, detail='Only SuperUser, FranchiseUser or Finance users can delete IRP5 documents')
    _get_manageable_document(db, current_user, document_id)
    db.execute(text("""
        UPDATE irp5_documents
        SET is_active = FALSE, updated_at = :updated_at
        WHERE id = :id
    """), {'id': document_id, 'updated_at': datetime.utcnow()})
    db.commit()
    return {'message': 'IRP5 document deleted'}
