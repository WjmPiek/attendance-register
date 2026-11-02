from datetime import datetime
from decimal import Decimal
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api import commission, franchise_staff
from app.services import commission_automation as auto, email_service
from tests.test_mortuary_book import database, import_payload, quote_and_import
from tests.test_commission_payment_proof import manual_setup, payload
from tests.test_receipt_commissions import OWNER, stage_receipt
from tests.test_service_claims import STAFF, evidence


@pytest.fixture
def delivery_db(database):
    for sql in [
        'CREATE TABLE commission_delivery_settings(franchise_user_id INT PRIMARY KEY,recipient_email TEXT,updated_by_user_id INT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)',
        "CREATE TABLE commission_monthly_reports(id INTEGER PRIMARY KEY,franchise_user_id INT,month_key TEXT,period_start DATE,period_end DATE,send_on TEXT,recipient_email TEXT,subject TEXT,message TEXT,status TEXT DEFAULT 'scheduled',sent_at TEXT,error_message TEXT,next_attempt_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(franchise_user_id,month_key))",
        'CREATE TABLE commission_monthly_report_items(entry_id INT PRIMARY KEY,report_id INT)',
    ]:
        database.execute(text(sql))
    database.commit()
    return database


def settings(month='2026-11', **changes):
    return commission.DeliverySettingsIn(**dict({'recipient_email': 'finance@example.com', 'month_key': month,
        'period_start': '2026-10-25', 'period_end': '2026-11-25', 'send_on': '2026-11-27T08:00:00'}, **changes))


def test_own_verified_claim_approves_immediately_without_human_reviewer(database):
    manual_setup(database); evidence(database)
    saved = commission.create_entry(payload(), STAFF, database)
    assert saved['status'] == 'approved' and saved['reviewed_by_user_id'] is None
    assert json.loads(saved['source_metadata'])['automatic_approval']
    assert commission.entries(current_user=STAFF, db=database)['total'] == 100


def test_delayed_proof_auto_approves_once_and_never_bypasses_missing_invoice(database):
    manual_setup(database)
    saved = commission.create_entry(payload(), STAFF, database)
    quote_and_import(database, import_payload())
    stage_receipt(database, people=(), with_invoice=False)
    assert auto.auto_approve_holder(database, 2) == 0
    assert database.execute(text('SELECT status FROM commission_entries')).scalar() == 'pending'
    evidence(database)
    assert auto.auto_approve_holder(database, 2) == 2  # Claim plus the other enabled staff member's removal.
    database.commit()
    assert auto.auto_approve_holder(database, 2) == 0
    row = database.execute(text('SELECT * FROM commission_entries WHERE id=:id'), {'id': saved['id']}).mappings().one()
    assert row['status'] == 'approved' and row['reviewed_by_user_id'] is None
    assert json.loads(row['source_metadata'])['automatic_approval']


def test_import_commissions_auto_approve_once_with_existing_vat_calculation(database):
    from tests.test_receipt_commissions import configure
    configure(database)
    quote_and_import(database, import_payload()); stage_receipt(database)
    assert auto.auto_approve_holder(database, 2) == 4
    database.commit()
    assert auto.auto_approve_holder(database, 2) == 0
    rows = database.execute(text("SELECT * FROM commission_entries WHERE commission_type='invoice_commission' AND employee_user_id=11")).mappings().one()
    assert Decimal(str(rows['calculated_amount'])) == Decimal('410.10')
    assert rows['reviewed_by_user_id'] is None


def test_changed_name_or_disabled_category_keeps_claim_blocked(database):
    manual_setup(database)
    saved = commission.create_entry(payload().model_copy(update={'claim_deceased': 'Different Person'}), STAFF, database)
    evidence(database)
    auto.auto_approve_holder(database, 2)
    assert database.execute(text('SELECT status FROM commission_entries WHERE id=:id'), {'id': saved['id']}).scalar() == 'pending'


def test_default_cycle_and_send_date():
    value = auto.default_report(datetime(2027, 1, 5))
    assert str(value['period_start']) == '2026-12-25'
    assert str(value['period_end']) == '2027-01-25'
    assert value['send_on'] == datetime(2027, 1, 27, 8)


def test_holder_can_move_cutoff_and_send_date_staff_cannot(delivery_db):
    db = delivery_db
    commission.save_delivery_settings(settings(period_end='2026-11-28', send_on='2026-11-30T09:30:00'), OWNER, db)
    row = commission.delivery_settings(month='2026-11', current_user=OWNER, db=db)['report']
    assert row['period_end'] == '2026-11-28' and row['send_on'].startswith('2026-11-30 09:30')
    with pytest.raises(HTTPException, match='holder'):
        commission.save_delivery_settings(settings(), STAFF, db)
    with pytest.raises(HTTPException, match='cutoff'):
        commission.save_delivery_settings(settings(period_end='2026-11-28'), OWNER, db)


def test_monthly_email_is_once_only_and_no_email_before_due(delivery_db, monkeypatch):
    db = delivery_db; manual_setup(db); evidence(db)
    saved = commission.create_entry(payload(), STAFF, db)
    commission.save_delivery_settings(settings(), OWNER, db)
    sent = []
    monkeypatch.setattr(email_service, 'send_smtp_email', lambda email, subject, body: (sent.append((email, subject, body)) or ('sent', datetime(2026, 11, 27, 8), None, {})))
    auto.send_due_reports(db, 2, datetime(2026, 11, 26, 23))
    assert sent == []
    auto.send_due_reports(db, 2, datetime(2026, 11, 27, 8))
    auto.send_due_reports(db, 2, datetime(2026, 11, 28, 8))
    assert len(sent) == 1 and sent[0][0] == 'finance@example.com'
    assert 'Ewald Example: R 100.00' in sent[0][2] and f"#{saved['id']}" in sent[0][2]
    assert db.execute(text('SELECT COUNT(*) FROM commission_monthly_report_items')).scalar() == 1
    with pytest.raises(HTTPException, match='already been sent'):
        commission.save_delivery_settings(settings(), OWNER, db)


def test_late_approved_commissions_carry_forward_without_resending_older_entries(delivery_db, monkeypatch):
    db = delivery_db; manual_setup(db); evidence(db)
    first = commission.create_entry(payload(), STAFF, db)
    commission.save_delivery_settings(settings(), OWNER, db)
    messages = []
    monkeypatch.setattr(email_service, 'send_smtp_email', lambda email, subject, body: (messages.append(body) or ('sent', datetime(2026, 11, 27, 8), None, {})))
    auto.send_due_reports(db, 2, datetime(2026, 11, 27, 8))
    from app.services.receipt_commissions import save_branch_options
    db.execute(text("INSERT INTO commission_structures VALUES(2,2,'church_service','Church','fixed',60,NULL,TRUE)"))
    save_branch_options(db, 2, 11, {101: {'enabled_types': ['grave_service', 'church_service']}}, 1); db.commit()
    late = commission.create_entry(payload().model_copy(update={'commission_type': 'church_service'}), STAFF, db)
    auto.send_due_reports(db, 2, datetime(2026, 11, 28, 8))
    assert len(messages) == 1
    auto.send_due_reports(db, 2, datetime(2026, 12, 27, 8))
    assert len(messages) == 2 and f"#{late['id']} |" in messages[1]
    assert f"#{first['id']} |" not in messages[1]
    assert 'Earlier-period adjustment' in messages[1]


def test_known_email_failure_retries_but_uncertain_delivery_never_auto_resends(delivery_db, monkeypatch):
    db = delivery_db; manual_setup(db); evidence(db)
    commission.create_entry(payload(), STAFF, db)
    commission.save_delivery_settings(settings(), OWNER, db)
    attempts = []
    def failure(*args):
        attempts.append(1)
        return 'failed', None, 'SMTP not connected', {}
    monkeypatch.setattr(email_service, 'send_smtp_email', failure)
    auto.send_due_reports(db, 2, datetime(2026, 11, 27, 8))
    auto.send_due_reports(db, 2, datetime(2026, 11, 27, 8, 30))
    assert len(attempts) == 1
    assert db.execute(text('SELECT COUNT(*) FROM commission_monthly_report_items')).scalar() == 0
    monkeypatch.setattr(email_service, 'send_smtp_email', lambda *args: ('failed', None, 'Connection lost during delivery', {'delivery_uncertain': True}))
    auto.send_due_reports(db, 2, datetime(2026, 11, 27, 9))
    assert db.execute(text('SELECT status FROM commission_monthly_reports')).scalar() == 'uncertain'
    assert db.execute(text('SELECT COUNT(*) FROM commission_monthly_report_items')).scalar() == 1
    monkeypatch.setattr(email_service, 'send_smtp_email', lambda *args: pytest.fail('Must not resend uncertain delivery'))
    auto.send_due_reports(db, 2, datetime(2026, 11, 28, 9))


@pytest.mark.parametrize('kind', ['employee', 'manager'])
def test_staff_can_be_deactivated_and_reactivated_without_requiring_inactive_login_to_be_active(database, monkeypatch, kind):
    db = database
    if kind == 'manager':
        db.execute(text("INSERT INTO manager_users(id,user_id,franchise_user_id,name,surname,is_active) VALUES(11,11,2,'Ewald','Example',TRUE)"))
    for table in ['employee_users', 'manager_users', 'users']:
        db.execute(text(f'ALTER TABLE {table} ADD COLUMN updated_at TEXT'))
    db.commit()
    monkeypatch.setattr(franchise_staff, '_require_staff_manager', lambda *args: None)
    monkeypatch.setattr(franchise_staff, '_ensure_office_hours_columns', lambda *args: None)
    monkeypatch.setattr(franchise_staff, '_ensure_staff_identity_unique', lambda *args, **kwargs: None)
    monkeypatch.setattr(franchise_staff, '_ensure_user_role', lambda *args: None)
    monkeypatch.setattr(franchise_staff, '_ensure_franchise_exists', lambda *args: None)
    monkeypatch.setattr(franchise_staff, '_ensure_active_office_assignment', lambda *args: None)
    monkeypatch.setattr(franchise_staff, '_save_staff_commissions', lambda *args: None)
    monkeypatch.setattr(franchise_staff, '_staff_scope_filter', lambda db, user, table, uid: db.execute(text(f'SELECT * FROM {table} WHERE id=:id'), {'id': uid}).mappings().one())
    fn = franchise_staff.update_employee if kind == 'employee' else franchise_staff.update_manager
    model = franchise_staff.UpdateEmployeeRequest if kind == 'employee' else franchise_staff.UpdateManagerRequest
    fn(11, model(is_active=False), OWNER, db)
    assert not db.execute(text('SELECT is_active FROM users WHERE id=11')).scalar()
    with pytest.raises(HTTPException):
        franchise_staff._ensure_user_exists(db, 11)
    fn(11, model(is_active=True), OWNER, db)
    assert db.execute(text('SELECT is_active FROM users WHERE id=11')).scalar()


def test_inactive_staff_exception_never_accepts_a_missing_login(database):
    with pytest.raises(HTTPException):
        franchise_staff._ensure_user_exists(database, 123456, require_active=False)
