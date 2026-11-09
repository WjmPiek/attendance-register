from copy import deepcopy
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
import json
import sqlite3

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import mortuary, franchise_staff
from app.services.mortuary import DEFAULT_WEEK, match_employee, parse_pdf, parse_register_text, price_removal, public_holidays


SAMPLE = '''MARTINS FUNERALS EXAMPLE
MORTUARY BOOK REGISTER DETAILS
Branch Name EXAMPLE Date Generated 02 Nov 2026
MF Number TEST-1315 Body Number N/A
Name and Surname of Deceased Example Person
ID Number 0000000000000 Age 85 Sex MALE
Driver Ewald
Collected At Example location
Driver In Ewald and Aubrey
Date In 25 Oct 2026 Time In 23h45
Driver Out
Date Out Time Out
'''


def policy():
    return {'week': deepcopy(DEFAULT_WEEK), 'rates': {'driver_in': '100', 'driver_out': '200', 'assistant_in': '80', 'assistant_out': '150'}, 'extra_holidays': []}


def record():
    return dict(parse_register_text(SAMPLE), filename='example.pdf', source_hash='a' * 64, page=1)


def test_parse_original_print_layout_and_two_names():
    result = record()
    assert result['reference'] == 'TEST-1315'
    assert result['service_date'] == '2026-11-02'
    assert result['date_in'] == '2026-10-25'
    assert result['time_in'] == '23:45'
    assert result['names'] == ['Ewald', 'Aubrey']
    assert result['id_number'] == '0000000000000'
    assert result['branch'] == 'EXAMPLE'


def test_batch_pdf_collects_errors_without_silently_discarding_pages():
    stream = BytesIO()
    pdf = canvas.Canvas(stream)
    for content in (SAMPLE, 'Not a Mortuary Book register', SAMPLE.replace('TEST-1315', 'TEST-1316')):
        for i, line in enumerate(content.splitlines()):
            pdf.drawString(25, 800 - i * 18, line)
        pdf.showPage()
    pdf.save()
    records, errors = parse_pdf(stream.getvalue())
    assert [r['page'] for r in records] == [1, 3]
    assert len(errors) == 1 and errors[0]['page'] == 2


@pytest.mark.parametrize('day,at,expected', [
    ('2026-11-02', '07:59', 'out'), ('2026-11-02', '08:00', 'in'),
    ('2026-11-02', '16:59', 'in'), ('2026-11-02', '17:00', 'out'),
    ('2026-11-07', '08:00', 'in'), ('2026-11-07', '12:59', 'in'),
    ('2026-11-07', '13:00', 'out'), ('2026-11-08', '10:00', 'out'),
    ('2026-12-25', '10:00', 'out'), ('2026-08-10', '10:00', 'out'),
    ('2026-04-03', '10:00', 'out'), ('2026-04-06', '10:00', 'out'),
])
def test_business_hours_and_public_holidays(day, at, expected):
    r = dict(record(), date_in=day, time_in=at)
    assert price_removal(r, 'driver', policy())['band'] == expected


def test_employee_hours_closed_days_role_rates_and_standard_calendar():
    p = policy()
    p['week'][0] = {'start': '09:00', 'end': '15:00'}
    r = dict(record(), date_in='2026-11-02', time_in='08:30')
    assert price_removal(r, 'driver', p)['amount'] == '200.00'
    assert price_removal(r, 'assistant', p)['amount'] == '150.00'
    r['time_in'] = '10:00'
    assert price_removal(r, 'driver', p)['amount'] == '100.00'
    assert price_removal(r, 'driver', p, ['2026-11-02'])['band'] == 'in'
    p['week'][0] = None
    assert price_removal(r, 'driver', p)['band'] == 'out'


def test_holiday_calendar_and_inherited_employee_rates():
    assert date(2027, 3, 22) in public_holidays(2027)
    assert date(2024, 5, 29) in public_holidays(2024)
    default = policy()
    own = policy()
    own['rates'] = {k: None for k in mortuary.RATE_KEYS}
    own['rates']['assistant_out'] = '175'
    merged = mortuary.effective_policy({0: default, 11: own}, 11)
    assert merged['rates']['driver_out'] == '200'
    assert merged['rates']['assistant_out'] == '175'
    assert default['rates']['assistant_out'] == '150'


def test_matching_never_guesses_between_shared_first_names():
    people = [{'user_id': 11, 'full_name': 'Ewald Example'}, {'user_id': 12, 'full_name': 'Aubrey Example'}]
    assert match_employee('Ewald', people) == 11
    assert match_employee('Aubrey', people) == 12
    assert match_employee('Unknown', people) is None
    people.append({'user_id': 13, 'full_name': 'Ewald Another'})
    assert match_employee('Ewald', people) is None
    assert match_employee('Ewald Another', people) == 13


def test_bad_documents_and_incomplete_fields_are_rejected():
    with pytest.raises(ValueError):
        parse_pdf(b'not a PDF')
    with pytest.raises(ValueError, match='Required field missing'):
        parse_register_text(SAMPLE.replace('Driver In Ewald and Aubrey', 'Driver In'))
    with pytest.raises(ValueError):
        parse_register_text(SAMPLE.replace('23h45', '99h99'))
    with pytest.raises(ValidationError):
        mortuary.Window(start='17:00', end='08:00')
    with pytest.raises(ValidationError):
        mortuary.Rates(driver_in='-1')


@pytest.fixture
def database(monkeypatch):
    sqlite3.register_adapter(Decimal, str)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    connection = engine.raw_connection()
    connection.create_function('NOW', 0, lambda: '2026-11-02 12:00:00')
    connection.create_function('pg_advisory_xact_lock', 2, lambda *a: 1)
    connection.create_function('CONCAT', -1, lambda *parts: ''.join(str(p) for p in parts if p is not None))
    connection.close()
    with Session(engine) as db:
        schemas = [
            "CREATE TABLE commission_monthly_reports(id INTEGER PRIMARY KEY,franchise_user_id INT,month_key TEXT,period_start DATE,period_end DATE,send_on TEXT,recipient_email TEXT,subject TEXT,message TEXT,pdf_content BLOB,status TEXT DEFAULT 'scheduled',sent_at TEXT,error_message TEXT,next_attempt_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(franchise_user_id,month_key))",
            'CREATE TABLE commission_monthly_report_items(entry_id INT PRIMARY KEY,report_id INT)',
            '''CREATE TABLE commission_carry_forwards(entry_id INT,source_report_id INT,source_month TEXT,target_month TEXT,
                target_start DATE,target_end DATE,estimated_amount NUMERIC,reason TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(entry_id,source_report_id))''',
            'CREATE TABLE mortuary_policies(franchise_user_id INT,employee_user_id INT,policy TEXT,updated_by_user_id INT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(franchise_user_id,employee_user_id))',
            '''CREATE TABLE commission_entries(id INTEGER PRIMARY KEY,franchise_user_id INT,employee_user_id INT,commission_type TEXT,service_date DATE,reference TEXT,quantity NUMERIC,applied_rate NUMERIC,calculated_amount NUMERIC,notes TEXT,branch_name TEXT,created_by_user_id INT,status TEXT,submitted_at TEXT,reviewed_at TEXT,reviewed_by_user_id INT,last_edited_by_user_id INT,is_cancelled BOOLEAN DEFAULT FALSE)''',
            '''CREATE TABLE mortuary_import_allocations(id INTEGER PRIMARY KEY,franchise_user_id INT,employee_user_id INT,branch_key TEXT,reference_key TEXT,entry_id INT,source_hash TEXT,source_filename TEXT,source_page INT,removal_role TEXT,date_in DATE,time_in TEXT,fee_band TEXT,UNIQUE(franchise_user_id,employee_user_id,branch_key,reference_key))''',
            'CREATE TABLE commission_entry_audit(id INTEGER PRIMARY KEY,entry_id INT,action TEXT,actor_user_id INT,old_values TEXT,new_values TEXT,note TEXT)',
            '''CREATE TABLE notifications(id INTEGER PRIMARY KEY,user_id INT,recipient_user_id INT,notification_type TEXT,subject TEXT,message TEXT,status TEXT,is_read BOOLEAN,severity TEXT,target_tab TEXT,related_table TEXT,related_id INT,created_at TEXT)''',
        ]
        schemas += [
            'CREATE TABLE users(id INTEGER PRIMARY KEY,full_name TEXT,email TEXT,is_active BOOLEAN)',
            'CREATE TABLE franchise_users(id INTEGER PRIMARY KEY,user_id INT,franchise_name TEXT,business_name TEXT,trading_as TEXT,vat_number TEXT,is_active BOOLEAN)',
            'CREATE TABLE employee_users(id INTEGER PRIMARY KEY,user_id INT,franchise_user_id INT,manager_user_id INT,name TEXT,surname TEXT,employee_number TEXT,employee_role TEXT,is_active BOOLEAN)',
            'CREATE TABLE manager_users(id INTEGER PRIMARY KEY,user_id INT,franchise_user_id INT,name TEXT,surname TEXT,employee_number TEXT,is_active BOOLEAN)',
            'CREATE TABLE attendance_branches(id INTEGER PRIMARY KEY,franchise_user_id INT,main_franchise_id INT,name TEXT,vat_number TEXT,is_active BOOLEAN DEFAULT TRUE,main_synced BOOLEAN DEFAULT FALSE)',
            'CREATE TABLE employee_branch_assignments(franchise_user_id INT,employee_user_id INT PRIMARY KEY,branch_id INT,can_import_commissions BOOLEAN DEFAULT FALSE)',
            'CREATE TABLE employee_commission_options(franchise_user_id INT,employee_user_id INT,commission_type TEXT,enabled BOOLEAN,rate NUMERIC,updated_by_user_id INT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(franchise_user_id,employee_user_id,commission_type))',
            'CREATE TABLE employee_commission_branch_options(franchise_user_id INT,employee_user_id INT,commission_type TEXT,branch_id INT,rate NUMERIC,PRIMARY KEY(franchise_user_id,employee_user_id,commission_type,branch_id))',
            'CREATE TABLE receipt_commission_settings(franchise_user_id INT,branch_id INT DEFAULT 0,vat_registered BOOLEAN,vat_number TEXT,vat_rate NUMERIC,receipt_percentage NUMERIC,updated_by_user_id INT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(franchise_user_id,branch_id))',
            'CREATE TABLE commission_documents(id INTEGER PRIMARY KEY,franchise_user_id INT,kind TEXT,branch_key TEXT,mf_key TEXT,document_key TEXT,source_data TEXT,source_hash TEXT,created_by_user_id INT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,deleted_at TEXT,deleted_by_user_id INT,deletion_reason TEXT)',
            'CREATE TABLE commission_document_staff(document_id INT,employee_user_id INT,removal_role TEXT,PRIMARY KEY(document_id,employee_user_id))',
        ]
        schemas.append('CREATE TABLE employee_commission_branch_overrides(franchise_user_id INT,employee_user_id INT,branch_id INT,rates TEXT DEFAULT \'{}\',PRIMARY KEY(franchise_user_id,employee_user_id,branch_id))')
        for schema in schemas:
            db.execute(text(schema))
        db.execute(text('CREATE UNIQUE INDEX uq_active_document ON commission_documents(franchise_user_id,kind,branch_key,document_key) WHERE deleted_at IS NULL'))
        schemas_files = 'CREATE TABLE commission_document_files(franchise_user_id INT,source_hash TEXT,filename TEXT,file_content BLOB,uploaded_by_user_id INT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(franchise_user_id,source_hash))'
        db.execute(text(schemas_files))
        db.execute(text('CREATE TABLE external_commission_branches(branch_id INT PRIMARY KEY,franchise_user_id INT,branch_key TEXT,created_by_user_id INT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(franchise_user_id,branch_key))'))
        db.execute(text("CREATE TABLE commission_branch_rates(franchise_user_id INT,branch_id INT,rates TEXT,updated_by_user_id INT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(franchise_user_id,branch_id))"))
        for column in ('mortuary_document_id INT', 'receipt_document_id INT', 'invoice_document_id INT', 'source_metadata TEXT', 'invoice_value_before_tax NUMERIC', 'hours NUMERIC', 'hourly_rate NUMERIC', 'earning_branch_id INT', 'review_notes TEXT', 'updated_at TEXT'):
            db.execute(text('ALTER TABLE commission_entries ADD COLUMN ' + column))
        db.execute(text("CREATE UNIQUE INDEX uq_receipt_award ON commission_entries(receipt_document_id,employee_user_id) WHERE commission_type='invoice_commission' AND receipt_document_id IS NOT NULL"))
        db.execute(text("CREATE UNIQUE INDEX uq_book_award ON commission_entries(mortuary_document_id,employee_user_id) WHERE commission_type='removals' AND mortuary_document_id IS NOT NULL"))
        db.execute(text("CREATE UNIQUE INDEX uq_invoice_award ON commission_entries(invoice_document_id,employee_user_id) WHERE commission_type='invoice_commission' AND invoice_document_id IS NOT NULL"))
        for uid,name in ((1,'Owner'),(11,'Ewald Example'),(12,'Aubrey Example'),(99,'Foreign Staff')):
            db.execute(text('INSERT INTO users VALUES(:uid,:name,NULL,TRUE)'), {'uid':uid,'name':name})
        db.execute(text("INSERT INTO franchise_users VALUES(2,1,'EXAMPLE','EXAMPLE',NULL,NULL,TRUE),(99,99,'FOREIGN','FOREIGN',NULL,NULL,TRUE)"))
        db.execute(text("INSERT INTO employee_users VALUES(11,11,2,NULL,'Ewald','Example','11','Driver',TRUE),(12,12,2,NULL,'Aubrey','Example','12','Employee',TRUE),(99,99,99,NULL,'Foreign','Staff','99','Employee',TRUE)"))
        db.execute(text("INSERT INTO attendance_branches VALUES(101,2,1,'EXAMPLE',NULL,TRUE,TRUE),(102,2,2,'EXAMPLE SOUTH',NULL,TRUE,TRUE),(900,99,9,'FOREIGN',NULL,TRUE,TRUE)"))
        db.execute(text('INSERT INTO employee_branch_assignments VALUES(2,11,101,FALSE),(2,12,102,FALSE),(99,99,900,FALSE)'))
        db.execute(text('INSERT INTO mortuary_policies VALUES(2,0,:p,1,NOW())'), {'p': json.dumps(policy())})
        for staff_table in ('employee_users', 'manager_users'):
            db.execute(text(f"ALTER TABLE {staff_table} ADD COLUMN work_start_time TEXT DEFAULT '08:00'"))
            db.execute(text(f"ALTER TABLE {staff_table} ADD COLUMN work_end_time TEXT DEFAULT '17:00'"))
            db.execute(text(f'ALTER TABLE {staff_table} ADD COLUMN work_week TEXT'))
        db.commit()
        def scope(db, user, fid):
            if user.id != 1 or fid not in (2, None):
                raise HTTPException(403, 'Outside scope')
            return 2
        monkeypatch.setattr(franchise_staff, '_staff_franchise_id', scope)
        monkeypatch.setattr(mortuary, '_staff_franchise_id', scope)
        from app.api import commission, receipt_commissions
        monkeypatch.setattr(receipt_commissions, '_staff_franchise_id', scope)
        monkeypatch.setattr(commission, '_profile', lambda db, user: ({'FranchiseUser'} if user.id==1 else {'EmployeeUser'}, 2 if user.id!=99 else 99, None, user.id, 'franchise' if user.id==1 else 'employee'))
        def participant(db,user,uid,write=False):
            if uid not in (11,12) or (user.id!=1 and uid!=user.id):
                raise HTTPException(403,'Outside scope')
            return {'user_id':uid,'franchise_user_id':2,'full_name': 'Ewald Example' if uid==11 else 'Aubrey Example'}
        monkeypatch.setattr(mortuary, '_participant', participant)
        monkeypatch.setattr(receipt_commissions, '_participant', participant)
        monkeypatch.setattr(commission, '_participant', participant)
        from app.services import commission_automation
        monkeypatch.setattr(commission_automation, 'SessionLocal', lambda: Session(engine))
        yield db
    engine.dispose()


def import_payload(records=None):
    records = records or [record()]
    token = mortuary.signer().dumps({'kind': 'preview', 'user_id': 1, 'franchise_user_id': 2, 'records': records})
    return mortuary.ImportIn(preview_token=token, confirmed_franchise=True, allocations=[
        {'record': i, 'name_index': n, 'employee_user_id': uid, 'role': role}
        for i in range(len(records)) for n, uid, role in [(0, 11, 'driver'), (1, 12, 'assistant')]
    ])


def quote_and_import(db, payload):
    q = mortuary.quote(payload, SimpleNamespace(id=1), db)
    payload.quote_token = q['quote_token']
    return mortuary.import_books(payload, SimpleNamespace(id=1), db)


def test_twenty_books_are_evidence_only_until_receipts_are_matched(database):
    records = [dict(record(), reference=f'TEST-{i}') for i in range(20)]
    payload = import_payload(records)
    result = quote_and_import(database, payload)
    assert result['created'] == 0 and result['saved_books'] == 20
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar() == 0
    assert database.execute(text('SELECT COUNT(*) FROM commission_document_staff')).scalar() == 40
    again = quote_and_import(database, payload)
    assert again['saved_books'] == 0 and again['skipped_duplicates'] == 20
    changed = import_payload([dict(records[0], service_date='2026-11-05')])
    assert quote_and_import(database, changed)['saved_books'] == 0


def test_changed_quote_is_rejected_but_books_can_wait_for_missing_fees(database):
    payload = import_payload()
    q = mortuary.quote(payload, SimpleNamespace(id=1), database)
    payload.quote_token = q['quote_token']
    changed = policy(); changed['rates']['driver_out'] = None
    database.execute(text('UPDATE mortuary_policies SET policy=:p'), {'p': json.dumps(changed)})
    database.commit()
    with pytest.raises(HTTPException, match='changed'):
        mortuary.import_books(payload, SimpleNamespace(id=1), database)
    assert quote_and_import(database, payload)['saved_books'] == 1
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar() == 0


def test_ambiguous_or_foreign_allocations_and_unsigned_sources_are_blocked(database):
    payload = import_payload()
    payload.allocations[1].employee_user_id = 11
    with pytest.raises(HTTPException, match='different employees'):
        mortuary.quote(payload, SimpleNamespace(id=1), database)
    payload.allocations[1].employee_user_id = 99
    with pytest.raises(HTTPException, match='outside the holder'):
        mortuary.quote(payload, SimpleNamespace(id=1), database)
    payload = import_payload(); payload.allocations.pop()
    with pytest.raises(HTTPException, match='exactly once'):
        mortuary.quote(payload, SimpleNamespace(id=1), database)
    with pytest.raises(HTTPException, match='invalid'):
        mortuary.read_preview(import_payload().preview_token, 88)
    with pytest.raises(HTTPException, match='invalid'):
        mortuary.read_preview('tampered', 1)


def test_partial_book_stage_failure_rolls_back_the_batch(database, monkeypatch):
    from app.api import receipt_commissions
    original=receipt_commissions.save_document
    calls=[]
    def fail_second(*args, **kwargs):
        calls.append(True)
        if len(calls)==2: raise RuntimeError('Simulated failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(receipt_commissions,'save_document',fail_second)
    with pytest.raises(RuntimeError):
        quote_and_import(database, import_payload([record(),dict(record(),reference='TEST-2')]))
    assert database.execute(text('SELECT COUNT(*) FROM commission_documents')).scalar() == 0
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar() == 0


def test_http_upload_settings_quote_and_import(database, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user
    from app.db.session import get_db
    app = FastAPI()
    app.include_router(mortuary.router, prefix='/api/mortuary')
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_db] = lambda: database
    monkeypatch.setattr(mortuary, 'employees', lambda *args: [
        {'user_id': 11, 'full_name': 'Ewald Example'}, {'user_id': 12, 'full_name': 'Aubrey Example'}])
    client = TestClient(app)
    assert client.get('/api/mortuary/settings').status_code == 200
    save = client.put('/api/mortuary/settings', json=dict(policy(), employee_user_id=11))
    assert save.status_code == 200, save.text
    stream = BytesIO(); pdf = canvas.Canvas(stream)
    for i, line in enumerate(SAMPLE.splitlines()):
        pdf.drawString(25, 800 - i * 18, line)
    pdf.save()
    response = client.post('/api/mortuary/preview', files=[('files', ('example.pdf', stream.getvalue(), 'application/pdf'))])
    assert response.status_code == 200, response.text
    preview = response.json()
    assert [a['employee_user_id'] for a in preview['allocations']] == [11, 12]
    payload = {'preview_token': preview['preview_token'], 'allocations': preview['allocations'], 'confirmed_franchise': True}
    quote = client.post('/api/mortuary/quote', json=payload)
    assert quote.status_code == 200, quote.text
    assert Decimal(quote.json()['total']) == Decimal('350')
    payload['quote_token'] = quote.json()['quote_token']
    saved = client.post('/api/mortuary/import', json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()['created'] == 0
    assert saved.json()['saved_books'] == 1


def test_staff_scope_rejects_employees_managers_and_foreign_franchises(monkeypatch):
    for role in ('EmployeeUser', 'ManagerUser'):
        monkeypatch.setattr(franchise_staff, '_roles', lambda db, user: [role])
        with pytest.raises(HTTPException) as exc:
            franchise_staff._staff_franchise_id(None, SimpleNamespace(id=1), None)
        assert exc.value.status_code == 403
    monkeypatch.setattr(franchise_staff, '_roles', lambda db, user: ['FranchiseUser'])
    monkeypatch.setattr(franchise_staff, '_franchise_profile_id', lambda db, uid: 2)
    with pytest.raises(HTTPException) as exc:
        franchise_staff._staff_franchise_id(None, SimpleNamespace(id=1), 99)
    assert exc.value.status_code == 403

