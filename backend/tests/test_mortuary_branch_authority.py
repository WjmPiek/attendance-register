import json
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from app.api import receipt_commissions as api
from app.services.receipt_commissions import require_payment_proof, save_branch_options
from app.services.mf_evidence import resolve_record
from tests.test_mortuary_book import database,record,import_payload,quote_and_import
from tests.test_receipt_commissions import receipt,stage_receipt,stage_invoice
from tests.test_case_claims import setup,claim


def test_receipt_branding_follows_mf_book_branch_without_merging_rates(database):
    setup(database)
    save_branch_options(database,2,11,{102:{'enabled_types':['invoice_commission'],'rates':{'driver_invoice_commission':'5'}}},1,branch_id=102)
    database.commit()
    quote_and_import(database,import_payload())
    stage_receipt(database,[dict(receipt(),branch='EXAMPLE SOUTH')],people=())
    rows=database.execute(text('SELECT * FROM commission_documents')).mappings().all()
    assert {row['branch_key'] for row in rows}=={'example'}
    finance=[json.loads(row['source_data']) for row in rows if row['kind']!='mortuary']
    assert all(row['printed_branch']=='EXAMPLE SOUTH' and row['earning_branch_id']==101 for row in finance)
    assert require_payment_proof(database,2,101,'TEST1315')['invoice_number']=='1309'
    with pytest.raises(HTTPException):require_payment_proof(database,2,102,'TEST1315')
    result=claim(database)
    assert result['total']=='685.10' and result['status']=='pending'
    repeated=claim(database,102)
    assert repeated['branch_id']==101 and repeated['created']==0
    assert database.execute(text('SELECT rate FROM employee_commission_branch_options WHERE employee_user_id=11 AND branch_id=102 AND commission_type=\'invoice_commission\'')).scalar() is None
    assert database.execute(text('SELECT rates FROM employee_commission_branch_overrides WHERE employee_user_id=11 AND branch_id=102')).scalar()=='{"driver_invoice_commission": "5"}'


def test_evidence_uploaded_before_book_is_repaired_in_place(database):
    setup(database)
    source=dict(receipt(),branch='EXAMPLE SOUTH')
    stage_invoice(database,source)
    stage_receipt(database,[source],people=())
    before=[dict(row) for row in database.execute(text('SELECT id,source_hash FROM commission_documents')).mappings()]
    quote_and_import(database,import_payload())
    after=[dict(row) for row in database.execute(text("SELECT id,source_hash FROM commission_documents WHERE kind<>'mortuary'")).mappings()]
    assert after==before
    assert set(database.execute(text('SELECT branch_key FROM commission_documents')).scalars())=={'example'}
    assert database.execute(text("SELECT COUNT(*) FROM audit_logs WHERE action='evidence_matched_to_mortuary_branch'")).scalar()==2
    assert require_payment_proof(database,2,101,'MF TEST1315')


def test_same_mf_with_different_deceased_is_not_moved(database):
    setup(database);quote_and_import(database,import_payload())
    source=dict(receipt(),branch='EXAMPLE SOUTH',deceased='Other Person')
    assert resolve_record(database,2,'receipt',source)['branch']=='EXAMPLE SOUTH'


def test_multiple_matching_books_require_a_printed_branch_match(database):
    setup(database)
    quote_and_import(database,import_payload())
    quote_and_import(database,import_payload([dict(record(),branch='EXAMPLE SOUTH',source_hash='c'*64)]))
    with pytest.raises(HTTPException,match='ambiguous'):
        resolve_record(database,2,'receipt',dict(receipt(),branch='OTHER'))
    assert resolve_record(database,2,'receipt',dict(receipt(),branch='EXAMPLE SOUTH'))['earning_branch_id']==102


def test_foreign_holder_books_are_never_used(database):
    setup(database);quote_and_import(database,import_payload())
    source=dict(receipt(),branch='FOREIGN')
    assert resolve_record(database,99,'receipt',source)==source
