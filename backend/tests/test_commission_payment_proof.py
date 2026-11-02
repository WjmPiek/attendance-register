import json
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api import commission
from app.services.receipt_commissions import require_payment_proof, payment_eligibility, save_branch_options
from tests.test_mortuary_book import database, import_payload, quote_and_import
from tests.test_receipt_commissions import configure, receipt, stage_receipt, OWNER


def proof(db):
    return require_payment_proof(db, 2, 101, 'MF TEST-1315')


def test_both_documents_are_compulsory(database):
    configure(database)
    with pytest.raises(HTTPException, match='compulsory'):
        proof(database)
    quote_and_import(database, import_payload())
    with pytest.raises(HTTPException, match='compulsory'):
        proof(database)
    stage_receipt(database)
    result = proof(database)
    assert result['mortuary_document_id'] and result['receipt_document_id']


@pytest.mark.parametrize('change', [
    {'reference': 'OTHER-MF'}, {'branch': 'EXAMPLE SOUTH'},
    {'id_number': 'DIFFERENT'}, {'gross_received': '0'}, {'gross_received': '-100'},
])
def test_unrelated_or_unpaid_receipts_do_not_qualify(database, change):
    configure(database)
    quote_and_import(database, import_payload())
    stage_receipt(database, [dict(receipt(), **change)])
    with pytest.raises(HTTPException):
        proof(database)


def test_receipt_alone_and_other_holder_cannot_qualify(database):
    configure(database); stage_receipt(database)
    with pytest.raises(HTTPException):
        proof(database)
    quote_and_import(database, import_payload())
    with pytest.raises(HTTPException):
        require_payment_proof(database, 99, 900, 'TEST-1315')


def manual_setup(db):
    configure(db)
    db.execute(text('''CREATE TABLE commission_structures(id INTEGER PRIMARY KEY,franchise_user_id INT,
        commission_type TEXT,label TEXT,calculation_type TEXT,rate NUMERIC,overtime_multiplier NUMERIC,is_active BOOLEAN)'''))
    db.execute(text("INSERT INTO commission_structures VALUES(1,2,'grave_service','Grave service','fixed',100,NULL,TRUE)"))
    save_branch_options(db, 2, 11, {101: {'enabled_types': ['grave_service']}}, 1)
    db.commit()


def payload():
    return commission.EntryIn(employee_user_id=11, commission_type='grave_service', service_date='2026-11-02',
                              reference='TEST-1315', earning_branch_id=101)


def test_owner_cannot_bypass_proof_with_manual_approved_entry(database):
    manual_setup(database)
    with pytest.raises(HTTPException, match='compulsory'):
        commission.create_entry(payload(), OWNER, database)
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar() == 0
    quote_and_import(database, import_payload())
    stage_receipt(database, people=())
    entry = commission.create_entry(payload(), OWNER, database)
    saved = database.execute(text('SELECT * FROM commission_entries WHERE id=:id'), {'id': entry['id']}).mappings().one()
    assert saved['status'] == 'approved' and saved['mortuary_document_id'] and saved['receipt_document_id']
    assert payment_eligibility(database, saved)['payment_eligible']


@pytest.mark.parametrize('bulk', [False, True])
def test_single_and_bulk_approval_require_proof(database, monkeypatch, bulk):
    manual_setup(database)
    from types import SimpleNamespace
    submitted = commission.create_entry(payload(), SimpleNamespace(id=11), database)
    monkeypatch.setattr(commission, '_assert_review_allowed', lambda *args: None)
    with pytest.raises(HTTPException, match='compulsory'):
        if bulk:
            commission.bulk_review(commission.BulkReviewIn(entry_ids=[submitted['id']], status='approved'), OWNER, database)
        else:
            commission.review(submitted['id'], commission.ReviewIn(**payload().model_dump(), status='approved'), OWNER, database)
    assert database.execute(text('SELECT status FROM commission_entries')).scalar() == 'pending'


def test_legacy_approved_entry_is_retained_but_not_payable(database):
    configure(database)
    database.execute(text("INSERT INTO commission_entries(franchise_user_id,employee_user_id,commission_type,reference,earning_branch_id,status,calculated_amount) VALUES(2,11,'grave_service','TEST-1315',101,'approved',100)"))
    database.commit()
    report = commission.entries(current_user=OWNER, db=database)
    assert len(report['items']) == 1 and report['items'][0]['status'] == 'approved'
    assert report['total'] == Decimal(0) and not report['items'][0]['payment_eligible']
