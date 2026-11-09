import importlib.util
from io import BytesIO
from pathlib import Path
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from app.api import commission, receipt_commissions as receipts, mortuary
from app.services.audit import ensure_audit_log_table
from app.services.pending_removals import pending_rows
from app.services.receipt_commissions import save_branch_options
from tests.test_mortuary_book import database, record, import_payload, quote_and_import
from tests.test_receipt_commissions import configure, receipt, stage_invoice, stage_receipt, calculate, OWNER
from tests.test_document_register import client_for


def pending(db, **kwargs):
    return pending_rows(db,2,OWNER,**kwargs)


def test_saved_book_is_red_until_receipts_balance_then_only_green(database):
    configure(database)
    quote_and_import(database,import_payload())
    response=commission.entries(current_user=OWNER,db=database)
    assert response['items']==[] and response['total']==0
    assert sum(Decimal(r['expected_amount']) for r in response['pending_imports'])==350
    assert all(not r['payment_eligible'] and r['status']=='pending' for r in response['pending_imports'])
    assert not pending(database,employee_id=11,from_date=date(2026,10,1),to_date=date(2026,10,31))
    assert len(pending(database,employee_id=11,branch_id=101))==1
    assert not pending(database,employee_id=11,branch_id=102)
    stage_invoice(database,total='1150.00')
    stage_receipt(database,[dict(receipt(),gross_received='500.00')],people=())
    assert len(pending(database))==2
    ids=stage_receipt(database,[dict(receipt(),receipt_number='SECOND',gross_received='650.00',source_hash='c'*64)],people=())['document_ids']
    payload,_=calculate(database,ids);receipts.settle(payload,OWNER,database)
    response=commission.entries(current_user=OWNER,db=database)
    assert response['pending_imports']==[] and response['total']==350
    assert len(response['items'])==2
    assert all(r['payment_eligible'] for r in response['items'])


@pytest.mark.parametrize('day,time,amount,label',[('2026-11-02','09:00','100.00','Business hours'),('2026-11-02','19:00','200.00','After hours'),('2026-11-08','09:00','200.00','Sunday / public holiday')])
def test_pending_uses_correct_removal_fee_band(database,day,time,amount,label):
    configure(database)
    quote_and_import(database,import_payload([dict(record(),date_in=day,time_in=time)]))
    row=pending(database,employee_id=11)[0]
    assert row['expected_amount']==amount and row['fee_label']==label
    assert row['document_estimate']


def test_pending_respects_permissions_staff_privacy_rates_and_deleted_documents(database):
    configure(database);quote_and_import(database,import_payload())
    save_branch_options(database,2,11,{101:{'enabled_types':['removals'],'rates':{'driver_out':'275'}}},1)
    assert pending(database,employee_id=11)[0]['expected_amount']=='275.00'
    assert {r['employee_user_id'] for r in pending_rows(database,2,SimpleNamespace(id=11))}=={11}
    save_branch_options(database,2,11,{101:{'enabled_types':[]}},1)
    assert not pending(database,employee_id=11)
    database.execute(text('UPDATE commission_documents SET deleted_at=NOW()'))
    assert not pending(database)


def test_register_lists_only_populated_canonical_branches(database):
    configure(database);quote_and_import(database,import_payload())
    database.execute(text("UPDATE commission_documents SET created_at='2026-11-06 08:00:00'"))
    database.execute(text("INSERT INTO attendance_branches VALUES(801,2,NULL,'Martins EXAMPLE (F)',NULL,TRUE,FALSE)"))
    database.execute(text("INSERT INTO external_commission_branches VALUES(801,2,'example',1,NOW())"));database.commit()
    client,_=client_for(database)
    result=client.get('/api/commission-documents?month=2026-11').json()
    assert [b['id'] for b in result['branches']]==[101]
    assert result['cases'][0]['branch_id']==101
    assert client.get('/api/commission-documents?month=2026-10').json()['branches']==[]
    # A real linked branch with no uploads is valid to filter, but has no section.
    assert client.get('/api/commission-documents?month=2026-11&branch_id=102').json()['total']==0


def test_pending_outside_fee_is_separate_and_pdf_does_not_include_it_as_approved(database):
    configure(database)
    outside=receipts.declare_external_branch(receipts.ExternalBranchIn(name='OUTSIDE',vat_number='4000000000'),OWNER,database)
    save_branch_options(database,2,11,{101:{'enabled_types':['removals','service_other_branch'],'rates':{'driver_other_branch':'50'}}},1)
    quote_and_import(database,import_payload([dict(record(),branch='OUTSIDE',external_branch_id=outside['id'])]))
    rows=pending(database,employee_id=11)
    assert {r['commission_type'] for r in rows}=={'removals','service_other_branch'}
    assert sum(Decimal(r['expected_amount']) for r in rows)==250
    from pypdf import PdfReader
    from app.services.commission_pdf import build_commission_pdf
    result=build_commission_pdf([],rows,title='Pending removal report')
    content=' '.join(p.extract_text() for p in PdfReader(BytesIO(result)).pages)
    assert 'Waiting to be finalised: R 250.00' in content
    assert 'TOTAL APPROVED FOR FINANCE: R 0.00' in content


def test_cleanup_removes_only_unused_duplicate_and_records_audit(database):
    path=Path(__file__).parents[1]/'alembic/versions/023_remove_empty_duplicate_branches.py'
    spec=importlib.util.spec_from_file_location('cleanup_branches',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    ensure_audit_log_table(database)
    for bid,name in [(801,'Martins EXAMPLE (F)'),(802,'EXAMPLE'),(803,'Unlinked outside')]:
        database.execute(text('INSERT INTO attendance_branches VALUES(:id,2,NULL,:name,NULL,TRUE,FALSE)'),{'id':bid,'name':name})
        database.execute(text('INSERT INTO external_commission_branches VALUES(:id,2,:key,1,NOW())'),{'id':bid,'key':str(bid)})
    database.execute(text("INSERT INTO employee_commission_branch_overrides VALUES(2,11,802,'{}')"))
    assert migration.cleanup(database.connection())==[801]
    assert database.execute(text('SELECT count(*) FROM attendance_branches WHERE id IN (101,802,803)')).scalar()==3
    assert database.execute(text("SELECT count(*) FROM audit_logs WHERE action='unused_duplicate_branch_removed'")).scalar()==1
    assert migration.cleanup(database.connection())==[]


def test_invoice_percentage_is_red_on_its_service_branch_until_fully_paid(database):
    configure(database)
    save_branch_options(database,2,11,{101:{'enabled_types':['removals','invoice_commission']},102:{'enabled_types':['removals','invoice_commission'],'rates':{'driver_out':'300','driver_invoice_commission':'5'}}},1)
    quote_and_import(database,import_payload([dict(record(),branch='EXAMPLE SOUTH')]))
    source=dict(receipt(),branch='EXAMPLE SOUTH',service_date='2026-11-02')
    stage_invoice(database,source,total='1150')
    rows=pending(database,employee_id=11,branch_id=102)
    assert {r['commission_type']:Decimal(r['expected_amount']) for r in rows}=={'removals':Decimal(300),'invoice_commission':Decimal(50)}
    assert pending(database,employee_id=11,branch_id=101)==[]
    first=stage_receipt(database,[dict(source,gross_received='500')],people=(11,))
    assert next(r for r in pending(database,employee_id=11) if r['commission_type']=='invoice_commission')['expected_amount']=='50.00'
    ids=stage_receipt(database,[dict(source,receipt_number='PAYMENT2',gross_received='650',source_hash='c'*64)],people=(11,))['document_ids']
    payload,_=calculate(database,ids);receipts.settle(payload,OWNER,database)
    assert pending(database,employee_id=11)==[]
    result=commission.entries(employee_user_id=11,earning_branch_id=102,current_user=OWNER,db=database)
    assert result['total']==350 and len(result['items'])==2
    assert database.execute(text('SELECT branch_id FROM employee_branch_assignments WHERE employee_user_id=11')).scalar()==101


@pytest.mark.parametrize('category',['grave_service','full_funeral_service','cremation_service','church_service','joinings','overtime'])
def test_every_submitted_service_commission_waits_for_balanced_receipts(database,category):
    from tests.test_commission_payment_proof import manual_setup,payload
    from app.services.commission_automation import auto_approve_holder
    manual_setup(database)
    save_branch_options(database,2,11,{101:{'enabled_types':[category],'rates':{f'driver_{category}':'100'}}},1)
    request=payload().model_copy(update={'commission_type':category})
    claim=commission.create_entry(request,SimpleNamespace(id=11),database)
    assert claim['status']=='pending'
    quote_and_import(database,import_payload());stage_invoice(database,total='1150')
    stage_receipt(database,[dict(receipt(),gross_received='500')],people=())
    auto_approve_holder(database,2)
    entry=next(r for r in commission.entries(employee_user_id=11,current_user=OWNER,db=database)['items'] if r['id']==claim['id'])
    assert entry['status']=='pending' and not entry['payment_eligible']
    stage_receipt(database,[dict(receipt(),receipt_number='BALANCE',gross_received='650',source_hash='c'*64)],people=())
    auto_approve_holder(database,2)
    entry=next(r for r in commission.entries(employee_user_id=11,current_user=OWNER,db=database)['items'] if r['id']==claim['id'])
    assert entry['status']=='approved' and entry['payment_eligible'] and Decimal(entry['calculated_amount'])==100
