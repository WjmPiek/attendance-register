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


def test_employee_hours_closed_days_role_rates_and_extra_holiday():
    p = policy()
    p['week'][0] = {'start': '09:00', 'end': '15:00'}
    r = dict(record(), date_in='2026-11-02', time_in='08:30')
    assert price_removal(r, 'driver', p)['amount'] == '200.00'
    assert price_removal(r, 'assistant', p)['amount'] == '150.00'
    r['time_in'] = '10:00'
    assert price_removal(r, 'driver', p)['amount'] == '100.00'
    assert price_removal(r, 'driver', p, ['2026-11-02'])['band'] == 'out'
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
    connection.close()
    with Session(engine) as db:
        schemas = [
            'CREATE TABLE mortuary_policies(franchise_user_id INT,employee_user_id INT,policy TEXT,updated_by_user_id INT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(franchise_user_id,employee_user_id))',
            '''CREATE TABLE commission_entries(id INTEGER PRIMARY KEY,franchise_user_id INT,employee_user_id INT,commission_type TEXT,service_date DATE,reference TEXT,quantity NUMERIC,applied_rate NUMERIC,calculated_amount NUMERIC,notes TEXT,branch_name TEXT,created_by_user_id INT,status TEXT,submitted_at TEXT,reviewed_at TEXT,reviewed_by_user_id INT,last_edited_by_user_id INT,is_cancelled BOOLEAN DEFAULT FALSE)''',
            '''CREATE TABLE mortuary_import_allocations(id INTEGER PRIMARY KEY,franchise_user_id INT,employee_user_id INT,branch_key TEXT,reference_key TEXT,entry_id INT,source_hash TEXT,source_filename TEXT,source_page INT,removal_role TEXT,date_in DATE,time_in TEXT,fee_band TEXT,UNIQUE(franchise_user_id,employee_user_id,branch_key,reference_key))''',
            'CREATE TABLE commission_entry_audit(id INTEGER PRIMARY KEY,entry_id INT,action TEXT,actor_user_id INT,old_values TEXT,new_values TEXT,note TEXT)',
            '''CREATE TABLE notifications(id INTEGER PRIMARY KEY,user_id INT,recipient_user_id INT,notification_type TEXT,subject TEXT,message TEXT,status TEXT,is_read BOOLEAN,severity TEXT,target_tab TEXT,related_table TEXT,related_id INT,created_at TEXT)''',
        ]
        for schema in schemas:
            db.execute(text(schema))
        db.execute(text('INSERT INTO mortuary_policies VALUES(2,0,:p,1,NOW())'), {'p': json.dumps(policy())})
        db.commit()
        def scope(db, user, fid):
            if user.id != 1 or fid not in (2, None):
                raise HTTPException(403, 'Outside scope')
            return 2
        monkeypatch.setattr(mortuary, '_staff_franchise_id', scope)
        monkeypatch.setattr(mortuary, '_participant', lambda db, user, uid, write=True: {
            'franchise_user_id': 99 if uid == 99 else 2,
            'full_name': {11: 'Ewald Example', 12: 'Aubrey Example'}.get(uid, 'Outside')})
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


def test_import_twenty_books_workhub_entries_totals_notes_and_idempotence(database):
    records = [dict(record(), reference=f'TEST-{i}') for i in range(20)]
    payload = import_payload(records)
    result = quote_and_import(database, payload)
    assert result['created'] == 40
    assert result['totals']['11']['total'] == Decimal('4000')
    assert result['totals']['12']['total'] == Decimal('3000')
    rows = database.execute(text('SELECT * FROM commission_entries')).mappings().all()
    assert all(r['commission_type'] == 'removals' and r['quantity'] == 1 and r['status'] == 'approved' for r in rows)
    assert all(r['service_date'] == '2026-11-02' and r['branch_name'] == 'EXAMPLE' for r in rows)
    assert 'Driver In: Ewald and Aubrey' in rows[0]['notes']
    assert 'ID Number: 0000000000000' in rows[0]['notes']
    assert 'Collected At: Example location' in rows[0]['notes']
    assert 'Time In: 23:45' in rows[0]['notes']
    assert database.execute(text('SELECT COUNT(*) FROM commission_entry_audit')).scalar() == 40
    again = quote_and_import(database, payload)
    assert again['created'] == 0 and again['skipped_duplicates'] == 40
    # Even a regenerated document with another service date cannot duplicate the MF.
    changed = import_payload([dict(records[0], service_date='2026-11-05')])
    assert quote_and_import(database, changed)['created'] == 0


def test_missing_fees_and_changed_quotes_prevent_writes(database):
    payload = import_payload()
    quote = mortuary.quote(payload, SimpleNamespace(id=1), database)
    payload.quote_token = quote['quote_token']
    changed = policy(); changed['rates']['driver_out'] = None
    database.execute(text('UPDATE mortuary_policies SET policy=:p'), {'p': json.dumps(changed)})
    database.commit()
    with pytest.raises(HTTPException, match='changed'):
        mortuary.import_books(payload, SimpleNamespace(id=1), database)
    with pytest.raises(HTTPException, match='missing'):
        quote_and_import(database, payload)
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar() == 0


def test_ambiguous_or_foreign_allocations_and_unsigned_sources_are_blocked(database):
    payload = import_payload()
    payload.allocations[1].employee_user_id = 11
    with pytest.raises(HTTPException, match='different employees'):
        mortuary.quote(payload, SimpleNamespace(id=1), database)
    payload.allocations[1].employee_user_id = 99
    with pytest.raises(HTTPException, match='outside this franchise'):
        mortuary.quote(payload, SimpleNamespace(id=1), database)
    payload = import_payload(); payload.allocations.pop()
    with pytest.raises(HTTPException, match='exactly once'):
        mortuary.quote(payload, SimpleNamespace(id=1), database)
    with pytest.raises(HTTPException, match='invalid'):
        mortuary.read_preview(import_payload().preview_token, 88)
    with pytest.raises(HTTPException, match='invalid'):
        mortuary.read_preview('tampered', 1)


def test_partial_failure_rolls_back_the_whole_import(database, monkeypatch):
    calls = []
    def fail_second(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            raise RuntimeError('Simulated write failure')
    monkeypatch.setattr(mortuary, '_notify', fail_second)
    with pytest.raises(RuntimeError):
        quote_and_import(database, import_payload())
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar() == 0
    assert database.execute(text('SELECT COUNT(*) FROM mortuary_import_allocations')).scalar() == 0


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
    assert saved.json()['created'] == 2


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
