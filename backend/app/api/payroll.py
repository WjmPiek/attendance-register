from datetime import date, datetime, timedelta
import calendar
import csv
import io
import re
import pyzipper
from fastapi.responses import Response

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.core import User, UserRole

router = APIRouter()


def _roles(db: Session, user: User) -> set[str]:
    return {ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()}


def _is_finance_employee(db: Session, user_id: int) -> bool:
    row = db.execute(text("""
        SELECT employee_role FROM employee_users
        WHERE user_id = :uid AND COALESCE(is_active, TRUE) = TRUE
        LIMIT 1
    """), {"uid": user_id}).mappings().first()
    return bool(row and "finance" in str(row["employee_role"] or "").strip().lower())


def _franchise_id_for_user(db: Session, user: User):
    r = _roles(db, user)
    if "FranchiseUser" in r:
        row = db.execute(text("SELECT id FROM franchise_users WHERE user_id = :uid AND COALESCE(is_active, TRUE)=TRUE LIMIT 1"), {"uid": user.id}).mappings().first()
        return row["id"] if row else None
    if "ManagerUser" in r or "EmployeeUser" in r:
        row = db.execute(text("""
            SELECT franchise_user_id FROM manager_users WHERE user_id = :uid AND COALESCE(is_active, TRUE)=TRUE
            UNION ALL
            SELECT franchise_user_id FROM employee_users WHERE user_id = :uid AND COALESCE(is_active, TRUE)=TRUE
            LIMIT 1
        """), {"uid": user.id}).mappings().first()
        return row["franchise_user_id"] if row else None
    return None


def _can_payroll(db: Session, user: User) -> bool:
    r = _roles(db, user)
    return "SuperUser" in r or "FranchiseUser" in r or _is_finance_employee(db, user.id)


def _ensure_tables(db: Session):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS payroll_settings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE,
            franchise_user_id INTEGER NULL,
            pay_frequency VARCHAR(40) NOT NULL DEFAULT 'monthly',
            basic_salary NUMERIC(12,2) NOT NULL DEFAULT 0,
            hourly_rate NUMERIC(12,2) NOT NULL DEFAULT 0,
            overtime_multiplier NUMERIC(5,2) NOT NULL DEFAULT 1.50,
            allowances NUMERIC(12,2) NOT NULL DEFAULT 0,
            deductions NUMERIC(12,2) NOT NULL DEFAULT 0,
            uif_percent NUMERIC(5,2) NOT NULL DEFAULT 1.00,
            paye_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NULL
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS payroll_runs (
            id SERIAL PRIMARY KEY,
            run_month DATE NOT NULL,
            user_id INTEGER NOT NULL,
            franchise_user_id INTEGER NULL,
            staff_name VARCHAR(255) NOT NULL,
            role VARCHAR(120) NULL,
            days_present NUMERIC(8,2) NOT NULL DEFAULT 0,
            leave_days NUMERIC(8,2) NOT NULL DEFAULT 0,
            late_count INTEGER NOT NULL DEFAULT 0,
            missing_sign_out_count INTEGER NOT NULL DEFAULT 0,
            gross_pay NUMERIC(12,2) NOT NULL DEFAULT 0,
            deductions NUMERIC(12,2) NOT NULL DEFAULT 0,
            net_pay NUMERIC(12,2) NOT NULL DEFAULT 0,
            status VARCHAR(40) NOT NULL DEFAULT 'draft',
            created_by_user_id INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NULL
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS payroll_imports (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            payroll_month DATE NULL,
            franchise_user_id INTEGER NULL,
            imported_by_user_id INTEGER NOT NULL,
            imported_at TIMESTAMP NOT NULL DEFAULT NOW(),
            rows_total INTEGER NOT NULL DEFAULT 0,
            rows_matched INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(40) NOT NULL DEFAULT 'processed'
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS payroll_import_rows (
            id SERIAL PRIMARY KEY,
            import_id INTEGER NOT NULL REFERENCES payroll_imports(id) ON DELETE CASCADE,
            row_number INTEGER NOT NULL,
            matched_user_id INTEGER NULL,
            employee_key VARCHAR(255) NULL,
            employee_name VARCHAR(255) NULL,
            email VARCHAR(255) NULL,
            basic_salary NUMERIC(12,2) NULL,
            hourly_rate NUMERIC(12,2) NULL,
            allowances NUMERIC(12,2) NULL,
            deductions NUMERIC(12,2) NULL,
            paye_percent NUMERIC(5,2) NULL,
            uif_percent NUMERIC(5,2) NULL,
            pay_frequency VARCHAR(40) NULL,
            overtime_multiplier NUMERIC(5,2) NULL,
            match_method VARCHAR(80) NULL,
            status VARCHAR(40) NOT NULL DEFAULT 'unmatched',
            message TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """))

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS payroll_payslips (
            id SERIAL PRIMARY KEY,
            import_id INTEGER NULL REFERENCES payroll_imports(id) ON DELETE SET NULL,
            user_id INTEGER NOT NULL,
            franchise_user_id INTEGER NULL,
            employee_key VARCHAR(255) NULL,
            original_filename VARCHAR(255) NOT NULL,
            zip_filename VARCHAR(255) NULL,
            file_content BYTEA NOT NULL,
            content_type VARCHAR(120) NOT NULL DEFAULT 'application/zip',
            uploaded_by_user_id INTEGER NOT NULL,
            uploaded_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """))

    
    for stmt in [
        "ALTER TABLE payroll_settings ADD COLUMN IF NOT EXISTS overtime_multiplier NUMERIC(5,2) NOT NULL DEFAULT 1.50",
        "ALTER TABLE payroll_settings ADD COLUMN IF NOT EXISTS allowances NUMERIC(12,2) NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_settings ADD COLUMN IF NOT EXISTS deductions NUMERIC(12,2) NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_settings ADD COLUMN IF NOT EXISTS uif_percent NUMERIC(5,2) NOT NULL DEFAULT 1.00",
        "ALTER TABLE payroll_settings ADD COLUMN IF NOT EXISTS paye_percent NUMERIC(5,2) NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_settings ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE payroll_imports ADD COLUMN IF NOT EXISTS rows_total INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_imports ADD COLUMN IF NOT EXISTS rows_matched INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE payroll_imports ADD COLUMN IF NOT EXISTS status VARCHAR(40) NOT NULL DEFAULT 'processed'",
        "ALTER TABLE payroll_import_rows ADD COLUMN IF NOT EXISTS matched_user_id INTEGER NULL",
        "ALTER TABLE payroll_import_rows ADD COLUMN IF NOT EXISTS employee_name VARCHAR(255) NULL",
        "ALTER TABLE payroll_import_rows ADD COLUMN IF NOT EXISTS status VARCHAR(40) NOT NULL DEFAULT 'unmatched'",
        "ALTER TABLE payroll_import_rows ADD COLUMN IF NOT EXISTS message TEXT NULL",
        "ALTER TABLE payroll_import_rows ADD COLUMN IF NOT EXISTS pay_frequency VARCHAR(40) NULL",
        "ALTER TABLE payroll_import_rows ADD COLUMN IF NOT EXISTS overtime_multiplier NUMERIC(5,2) NULL",
        "ALTER TABLE payroll_import_rows ADD COLUMN IF NOT EXISTS match_method VARCHAR(80) NULL",
    ]:
        db.execute(text(stmt))
    db.commit()


def _staff_scope_sql(db: Session, current_user: User):
    roles = _roles(db, current_user)
    if "SuperUser" in roles:
        return "1=1", {}
    fid = _franchise_id_for_user(db, current_user)
    if not fid:
        return "1=0", {}
    return "staff.franchise_user_id = :fid", {"fid": fid}


def _staff_rows(db: Session, current_user: User):
    where, params = _staff_scope_sql(db, current_user)
    rows = db.execute(text(f"""
        WITH staff AS (
            SELECT u.id AS user_id, e.franchise_user_id, e.name, e.surname, e.employee_role AS role, e.email,
                   e.employee_number, 'Employee' AS staff_type
            FROM employee_users e JOIN users u ON u.id = e.user_id
            WHERE COALESCE(e.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE
            UNION ALL
            SELECT u.id AS user_id, m.franchise_user_id, m.name, m.surname, 'Manager' AS role, m.email,
                   m.employee_number AS employee_number, 'Manager' AS staff_type
            FROM manager_users m JOIN users u ON u.id = m.user_id
            WHERE COALESCE(m.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE
        )
        SELECT staff.*, ps.basic_salary, ps.hourly_rate, ps.allowances, ps.deductions, ps.paye_percent, ps.uif_percent, ps.pay_frequency,
               COALESCE(ps.is_active, TRUE) AS payroll_active
        FROM staff
        LEFT JOIN payroll_settings ps ON ps.user_id = staff.user_id
        WHERE {where}
        ORDER BY staff.name, staff.surname
    """), params).mappings().all()
    return [dict(r) for r in rows]


class PayrollSettingIn(BaseModel):
    user_id: int
    basic_salary: float = 0
    hourly_rate: float = 0
    pay_frequency: str = "monthly"
    overtime_multiplier: float = 1.5
    allowances: float = 0
    deductions: float = 0
    uif_percent: float = 1
    paye_percent: float = 0
    is_active: bool = True


class PayrollRunIn(BaseModel):
    run_month: date = Field(description="Use first day of payroll month, for example 2026-04-01")
    save_run: bool = False


def _month_bounds(run_month: date):
    start = date(run_month.year, run_month.month, 1)
    last = calendar.monthrange(run_month.year, run_month.month)[1]
    end = date(run_month.year, run_month.month, last) + timedelta(days=1)
    return start, end


def _payroll_line(db: Session, row: dict, start: date, end: date):
    uid = int(row["user_id"])
    attendance = db.execute(text("""
        SELECT
          COUNT(DISTINCT DATE(created_at)) FILTER (WHERE action='sign_in') AS days_present,
          COUNT(*) FILTER (WHERE action='sign_in' AND COALESCE(is_late, FALSE)=TRUE) AS late_count,
          COUNT(*) FILTER (WHERE COALESCE(missing_sign_out, FALSE)=TRUE) AS missing_sign_out_count
        FROM attendance_events
        WHERE user_id = :uid AND created_at >= :start AND created_at < :end
    """), {"uid": uid, "start": start, "end": end}).mappings().first() or {}
    leave = db.execute(text("""
        SELECT COALESCE(SUM(days_requested),0) AS leave_days
        FROM leave_applications
        WHERE applicant_user_id = :uid AND status = 'approved'
          AND start_date < :end_date AND end_date >= :start_date
    """), {"uid": uid, "start_date": start, "end_date": end}).mappings().first() or {}
    basic = float(row.get("basic_salary") or 0)
    hourly = float(row.get("hourly_rate") or 0)
    allowances = float(row.get("allowances") or 0)
    base_pay = basic if basic > 0 else hourly * 8 * float(attendance.get("days_present") or 0)
    gross = round(base_pay + allowances, 2)
    uif = gross * (float(row.get("uif_percent") or 0) / 100.0)
    paye = gross * (float(row.get("paye_percent") or 0) / 100.0)
    fixed_deductions = float(row.get("deductions") or 0)
    deductions = round(uif + paye + fixed_deductions, 2)
    net = round(gross - deductions, 2)
    full_name = " ".join(x for x in [row.get("name") or "", row.get("surname") or ""] if x).strip() or f"User #{uid}"
    return {
        "user_id": uid,
        "franchise_user_id": row.get("franchise_user_id"),
        "staff_name": full_name,
        "role": row.get("role") or row.get("staff_type"),
        "days_present": float(attendance.get("days_present") or 0),
        "leave_days": float(leave.get("leave_days") or 0),
        "late_count": int(attendance.get("late_count") or 0),
        "missing_sign_out_count": int(attendance.get("missing_sign_out_count") or 0),
        "gross_pay": gross,
        "deductions": deductions,
        "net_pay": net,
    }


def _normalise_header(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower()).strip('_')


def _to_float(value):
    if value is None:
        return None
    text_value = str(value).strip()
    if text_value == '':
        return None
    text_value = text_value.replace('R', '').replace('r', '').replace(',', '').replace('%', '').strip()
    try:
        return float(text_value)
    except ValueError:
        return None


def _clean_match_text(value):
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _first(row: dict, *names):
    for name in names:
        if name in row and str(row[name]).strip() != '':
            return row[name]
    return ''


def _read_payroll_file(file: UploadFile):
    content = file.file.read()
    filename = (file.filename or '').lower()
    if filename.endswith('.xlsx') or filename.endswith('.xlsm'):
        try:
            from openpyxl import load_workbook
        except Exception as exc:
            raise HTTPException(status_code=400, detail='Excel import needs openpyxl installed. Add openpyxl to requirements.txt and reinstall backend requirements.') from exc
        wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [_normalise_header(h) for h in rows[0]]
        parsed = []
        for idx, values in enumerate(rows[1:], start=2):
            if not values or not any(v is not None and str(v).strip() for v in values):
                continue
            parsed.append({'_row_number': idx, **{headers[i]: values[i] if i < len(values) else '' for i in range(len(headers))}})
        return parsed
    if filename.endswith('.xls'):
        raise HTTPException(status_code=400, detail='Old .xls files are not supported directly. Save the payroll document as .xlsx or CSV, then import again.')
    
    if filename.endswith('.zip'):
        extracted_rows = []

        with pyzipper.AESZipFile(io.BytesIO(content)) as z:
            pdf_files = [f for f in z.namelist() if f.lower().endswith('.pdf')]

            if not pdf_files:
                raise HTTPException(status_code=400, detail='No PDF found inside ZIP file.')

            for idx, pdf_name in enumerate(pdf_files, start=1):
                code = pdf_name.split('/')[-1].replace('.PDF', '').replace('.pdf', '')
                employee_code = code[-6:]  # example: 102-NOR020 -> NOR020

                extracted_rows.append({
                    '_row_number': idx,
                    'empl_no': employee_code,
                    'payslip_filename': pdf_name,
                    'payslip_zip_bytes': content,
                })

        return extracted_rows


    if filename.endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail='Please upload the ZIP payroll export instead of the raw PDF.'
        )
    text_content = content.decode('utf-8-sig', errors='replace')
    sample = text_content[:2048]
    delimiter = ','
    if sample.count(';') > sample.count(','):
        delimiter = ';'
    if sample.count('\t') > sample.count(delimiter):
        delimiter = '\t'
    reader = csv.DictReader(io.StringIO(text_content), delimiter=delimiter)
    parsed = []
    for idx, row in enumerate(reader, start=2):
        norm = {_normalise_header(k): v for k, v in row.items() if k is not None}
        if any(str(v or '').strip() for v in norm.values()):
            norm['_row_number'] = idx
            parsed.append(norm)
    return parsed


def _last_7_digits(value) -> str:
    digits = re.sub(r'\D+', '', str(value or ''))
    return digits[-7:] if len(digits) >= 7 else ''


def _staff_match_maps(staff_rows):
    by_id, by_email, by_name, by_employee_last7 = {}, {}, {}, {}
    for s in staff_rows:
        uid = int(s['user_id'])
        by_id[str(uid)] = s
        email = str(s.get('email') or '').strip().lower()
        if email:
            by_email[email] = s
        full_name = _clean_match_text(' '.join(x for x in [s.get('name'), s.get('surname')] if x))
        if full_name:
            by_name[full_name] = s
        employee_last7 = _last_7_digits(s.get('employee_number'))
        if employee_last7:
            by_employee_last7[employee_last7] = s
    return by_id, by_email, by_name, by_employee_last7


def _match_payroll_staff(row: dict, by_id: dict, by_email: dict, by_name: dict, by_employee_last7: dict):
    user_key = str(_first(row, 'empl_no', 'empl_no_', 'employee_no', 'employee_number', 'employee_id', 'staff_id', 'emp_id', 'personnel_number', 'user_id')).strip()
    email = str(_first(row, 'email', 'email_address', 'employee_email', 'work_email')).strip().lower()
    employee_name = str(_first(row, 'employee', 'employee_name', 'staff_name', 'name', 'full_name', 'employee_full_name')).strip()
    user_key_last7 = _last_7_digits(user_key)
    if user_key_last7 and user_key_last7 in by_employee_last7:
        return by_employee_last7[user_key_last7], 'employee_number_last_7', user_key, email, employee_name
    if user_key and user_key in by_id:
        return by_id[user_key], 'user_id', user_key, email, employee_name
    if email and email in by_email:
        return by_email[email], 'email', user_key, email, employee_name
    cleaned_name = _clean_match_text(employee_name)
    if cleaned_name and cleaned_name in by_name:
        return by_name[cleaned_name], 'full_name', user_key, email, employee_name
    return None, 'unmatched', user_key, email, employee_name

@router.get('/employees')
def payroll_employees(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _can_payroll(db, current_user):
        raise HTTPException(status_code=403, detail='Payroll access denied')
    _ensure_tables(db)
    return _staff_rows(db, current_user)


@router.put('/settings')
def save_payroll_setting(payload: PayrollSettingIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _can_payroll(db, current_user):
        raise HTTPException(status_code=403, detail='Payroll access denied')
    _ensure_tables(db)
    staff = {int(s['user_id']): s for s in _staff_rows(db, current_user)}
    if int(payload.user_id) not in staff:
        raise HTTPException(status_code=404, detail='Selected employee is not in your payroll scope')
    fid = staff[int(payload.user_id)].get('franchise_user_id')
    
    db.execute(text("""
        INSERT INTO payroll_settings (user_id, franchise_user_id, pay_frequency, basic_salary, hourly_rate, overtime_multiplier,
            allowances, deductions, uif_percent, paye_percent, is_active, created_at, updated_at)
        VALUES (:user_id, :franchise_user_id, :pay_frequency, :basic_salary, :hourly_rate, :overtime_multiplier,
            :allowances, :deductions, :uif_percent, :paye_percent, :is_active, :now, :now)
        ON CONFLICT (user_id) DO UPDATE SET
            franchise_user_id = EXCLUDED.franchise_user_id,
            pay_frequency = EXCLUDED.pay_frequency,
            basic_salary = EXCLUDED.basic_salary,
            hourly_rate = EXCLUDED.hourly_rate,
            overtime_multiplier = EXCLUDED.overtime_multiplier,
            allowances = EXCLUDED.allowances,
            deductions = EXCLUDED.deductions,
            uif_percent = EXCLUDED.uif_percent,
            paye_percent = EXCLUDED.paye_percent,
            is_active = EXCLUDED.is_active,
            updated_at = EXCLUDED.updated_at
    """), {**payload.model_dump(), "franchise_user_id": fid, "now": datetime.utcnow()})
    db.commit()
    return {"success": True, "message": "Payroll settings saved"}


@router.post('/import-document')
def import_payroll_document(
    file: UploadFile = File(...),
    payroll_month: str = Form(''),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _can_payroll(db, current_user):
        raise HTTPException(status_code=403, detail='Payroll import access denied')
    _ensure_tables(db)
    rows = _read_payroll_file(file)
    staff_rows = _staff_rows(db, current_user)
    by_id, by_email, by_name, by_employee_last7 = _staff_match_maps(staff_rows)
    current_fid = _franchise_id_for_user(db, current_user)
    imported_at = datetime.utcnow()
    month_date = None
    if payroll_month:
        try:
            parsed_month = date.fromisoformat(payroll_month[:10])
            month_date = date(parsed_month.year, parsed_month.month, 1)
        except ValueError:
            month_date = None
    import_row = db.execute(text("""
        INSERT INTO payroll_imports (filename, payroll_month, franchise_user_id, imported_by_user_id, imported_at, rows_total, rows_matched)
        VALUES (:filename, :payroll_month, :franchise_user_id, :imported_by_user_id, :imported_at, 0, 0)
        RETURNING id
    """), {
        'filename': file.filename or 'payroll-import',
        'payroll_month': month_date,
        'franchise_user_id': current_fid,
        'imported_by_user_id': current_user.id,
        'imported_at': imported_at,
    }).mappings().first()
    import_id = import_row['id']
    results = []
    matched_count = 0
    for row in rows:
        row_no = int(row.get('_row_number') or len(results) + 1)
        staff, match_method, user_key, email, employee_name = _match_payroll_staff(row, by_id, by_email, by_name, by_employee_last7)
        basic_salary = _to_float(_first(row, 'basic_salary', 'basic_monthly_salary', 'salary', 'monthly_salary', 'gross_salary'))
        hourly_rate = _to_float(_first(row, 'hourly_rate', 'rate_per_hour'))
        allowances = _to_float(_first(row, 'allowances', 'allowance'))
        deductions = _to_float(_first(row, 'deductions', 'deduction'))
        paye_percent = _to_float(_first(row, 'paye_percent', 'paye', 'tax_percent'))
        uif_percent = _to_float(_first(row, 'uif_percent', 'uif'))
        overtime_multiplier = _to_float(_first(row, 'overtime_multiplier', 'ot_multiplier', 'overtime_rate'))
        pay_frequency = str(_first(row, 'pay_frequency', 'frequency', 'pay_cycle')).strip().lower() or None
        if pay_frequency and pay_frequency not in {'monthly', 'weekly', 'hourly'}:
            pay_frequency = None
        status = 'matched' if staff else 'unmatched'
        msg = f'Payroll settings updated by {match_method}' if staff else 'No matching employee in your allowed franchise scope'
        matched_user_id = int(staff['user_id']) if staff else None
        if staff:
            payslip_bytes = row.get('payslip_zip_bytes')
            payslip_filename = row.get('payslip_filename')

            if payslip_bytes and payslip_filename:
                db.execute(text("""
                    INSERT INTO payroll_payslips (
                        import_id, user_id, franchise_user_id, employee_key,
                        original_filename, zip_filename, file_content,
                        content_type, uploaded_by_user_id, uploaded_at
                    )
                    VALUES (
                        :import_id, :user_id, :franchise_user_id, :employee_key,
                        :original_filename, :zip_filename, :file_content,
                        :content_type, :uploaded_by_user_id, :uploaded_at
                    )
                """), {
                    'import_id': import_id,
                    'user_id': matched_user_id,
                    'franchise_user_id': staff.get('franchise_user_id'),
                    'employee_key': user_key,
                    'original_filename': payslip_filename,
                    'zip_filename': file.filename or 'payroll.zip',
                    'file_content': payslip_bytes,
                    'content_type': 'application/zip',
                    'uploaded_by_user_id': current_user.id,
                    'uploaded_at': imported_at,
                })
            matched_count += 1
            existing = db.execute(text("SELECT * FROM payroll_settings WHERE user_id = :uid"), {'uid': matched_user_id}).mappings().first() or {}
            db.execute(text("""
                INSERT INTO payroll_settings (user_id, franchise_user_id, pay_frequency, basic_salary, hourly_rate, overtime_multiplier,
                    allowances, deductions, uif_percent, paye_percent, is_active, created_at, updated_at)
                VALUES (:user_id, :franchise_user_id, COALESCE(:pay_frequency, 'monthly'), :basic_salary, :hourly_rate, :overtime_multiplier,
                    :allowances, :deductions, :uif_percent, :paye_percent, TRUE, :now, :now)
                ON CONFLICT (user_id) DO UPDATE SET
                    franchise_user_id = EXCLUDED.franchise_user_id,
                    basic_salary = EXCLUDED.basic_salary,
                    hourly_rate = EXCLUDED.hourly_rate,
                    overtime_multiplier = EXCLUDED.overtime_multiplier,
                    allowances = EXCLUDED.allowances,
                    deductions = EXCLUDED.deductions,
                    uif_percent = EXCLUDED.uif_percent,
                    paye_percent = EXCLUDED.paye_percent,
                    updated_at = EXCLUDED.updated_at
            """), {
                'user_id': matched_user_id,
                'franchise_user_id': staff.get('franchise_user_id'),
                'pay_frequency': pay_frequency or existing.get('pay_frequency') or 'monthly',
                'basic_salary': basic_salary if basic_salary is not None else float(existing.get('basic_salary') or 0),
                'hourly_rate': hourly_rate if hourly_rate is not None else float(existing.get('hourly_rate') or 0),
                'overtime_multiplier': overtime_multiplier if overtime_multiplier is not None else float(existing.get('overtime_multiplier') or 1.5),
                'allowances': allowances if allowances is not None else float(existing.get('allowances') or 0),
                'deductions': deductions if deductions is not None else float(existing.get('deductions') or 0),
                'uif_percent': uif_percent if uif_percent is not None else float(existing.get('uif_percent') or 1),
                'paye_percent': paye_percent if paye_percent is not None else float(existing.get('paye_percent') or 0),
                'now': imported_at,
            })
        db.execute(text("""
            INSERT INTO payroll_import_rows (import_id, row_number, matched_user_id, employee_key, employee_name, email,
                basic_salary, hourly_rate, allowances, deductions, paye_percent, uif_percent, pay_frequency, overtime_multiplier, match_method, status, message, created_at)
            VALUES (:import_id, :row_number, :matched_user_id, :employee_key, :employee_name, :email,
                :basic_salary, :hourly_rate, :allowances, :deductions, :paye_percent, :uif_percent, :pay_frequency, :overtime_multiplier, :match_method, :status, :message, :created_at)
        """), {
            'import_id': import_id,
            'row_number': row_no,
            'matched_user_id': matched_user_id,
            'employee_key': user_key or None,
            'employee_name': employee_name or None,
            'email': email or None,
            'basic_salary': basic_salary,
            'hourly_rate': hourly_rate,
            'allowances': allowances,
            'deductions': deductions,
            'paye_percent': paye_percent,
            'uif_percent': uif_percent,
            'pay_frequency': pay_frequency,
            'overtime_multiplier': overtime_multiplier,
            'match_method': match_method,
            'status': status,
            'message': msg,
            'created_at': imported_at,
        })
        results.append({
            'row_number': row_no,
            'status': status,
            'message': msg,
            'matched_user_id': matched_user_id,
            'employee_name': employee_name or ((' '.join(x for x in [staff.get('name'), staff.get('surname')] if x)) if staff else ''),
            'email': email,
            'basic_salary': basic_salary,
            'hourly_rate': hourly_rate,
            'allowances': allowances,
            'deductions': deductions,
            'pay_frequency': pay_frequency,
            'overtime_multiplier': overtime_multiplier,
            'match_method': match_method,
        })

        
    db.execute(text("UPDATE payroll_imports SET rows_total = :total, rows_matched = :matched WHERE id = :id"), {
        'total': len(results), 'matched': matched_count, 'id': import_id
    })
    db.commit()
    return {'import_id': import_id, 'filename': file.filename, 'rows_total': len(results), 'rows_matched': matched_count, 'rows': results}


@router.get('/imports')
def payroll_imports(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _can_payroll(db, current_user):
        raise HTTPException(status_code=403, detail='Payroll access denied')
    _ensure_tables(db)
    roles = _roles(db, current_user)
    fid = _franchise_id_for_user(db, current_user)
    if 'SuperUser' in roles:
        where, params = '1=1', {}
    else:
        where, params = 'franchise_user_id = :fid', {'fid': fid}
    rows = db.execute(text(f"SELECT * FROM payroll_imports WHERE {where} ORDER BY imported_at DESC LIMIT 25"), params).mappings().all()
    return [dict(r) for r in rows]


@router.post('/preview')
def preview_payroll(payload: PayrollRunIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _can_payroll(db, current_user):
        raise HTTPException(status_code=403, detail='Payroll access denied')
    _ensure_tables(db)
    start, end = _month_bounds(payload.run_month)
    rows = [_payroll_line(db, s, start, end) for s in _staff_rows(db, current_user) if s.get('payroll_active', True)]
    totals = {
        "gross_pay": round(sum(r["gross_pay"] for r in rows), 2),
        "deductions": round(sum(r["deductions"] for r in rows), 2),
        "net_pay": round(sum(r["net_pay"] for r in rows), 2),
        "staff_count": len(rows),
    }
    if payload.save_run:
        for r in rows:
            db.execute(text("""
                INSERT INTO payroll_runs (run_month, user_id, franchise_user_id, staff_name, role, days_present, leave_days,
                    late_count, missing_sign_out_count, gross_pay, deductions, net_pay, status, created_by_user_id, created_at)
                VALUES (:run_month, :user_id, :franchise_user_id, :staff_name, :role, :days_present, :leave_days,
                    :late_count, :missing_sign_out_count, :gross_pay, :deductions, :net_pay, 'draft', :created_by_user_id, :created_at)
            """), {**r, "run_month": start, "created_by_user_id": current_user.id, "created_at": datetime.utcnow()})
        db.commit()
    return {"run_month": str(start), "rows": rows, "totals": totals, "saved": payload.save_run}


@router.get('/runs')
def payroll_runs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _can_payroll(db, current_user):
        raise HTTPException(status_code=403, detail='Payroll access denied')
    _ensure_tables(db)
    where, params = _staff_scope_sql(db, current_user)
    rows = db.execute(text(f"""
        WITH staff AS (
            SELECT user_id, franchise_user_id FROM employee_users WHERE COALESCE(is_active, TRUE)=TRUE
            UNION ALL
            SELECT user_id, franchise_user_id FROM manager_users WHERE COALESCE(is_active, TRUE)=TRUE
        )
        SELECT pr.* FROM payroll_runs pr
        JOIN staff ON staff.user_id = pr.user_id
        WHERE {where}
        ORDER BY pr.run_month DESC, pr.staff_name ASC
        LIMIT 500
    """), params).mappings().all()
    return [dict(r) for r in rows]

@router.get('/my-payslips')
def my_payslips(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_tables(db)

    rows = db.execute(text("""
        SELECT
            id,
            employee_key,
            original_filename,
            zip_filename,
            uploaded_at
        FROM payroll_payslips
        WHERE user_id = :uid
        ORDER BY uploaded_at DESC
    """), {
        "uid": current_user.id
    }).mappings().all()

    return [dict(r) for r in rows]


@router.get('/payslips/{payslip_id}')
def download_payslip(
    payslip_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_tables(db)

    row = db.execute(text("""
        SELECT *
        FROM payroll_payslips
        WHERE id = :id
          AND user_id = :uid
        LIMIT 1
    """), {
        "id": payslip_id,
        "uid": current_user.id,
    }).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail='Payslip not found')

    return Response(
        content=row["file_content"],
        media_type='application/zip',
        headers={
            "Content-Disposition": f'attachment; filename="{row["zip_filename"]}"'
        }
    )
