from datetime import date
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import text

from app.api import commission_documents as register, receipt_commissions as receipts, mortuary, commission
from app.api.deps import get_current_user
from app.db.session import get_db
from app.services.attendance_branches import assign_staff
from app.services.receipt_commissions import branch_options, enabled_for_branch, save_branch_options
from tests.test_mortuary_book import database, record, SAMPLE, import_payload, quote_and_import
from tests.test_receipt_commissions import configure, receipt, stage_receipt, stage_invoice, calculate, OWNER
from tests.test_invoice_payment_proof import INVOICE


def client_for(db):
    app=FastAPI()
    app.include_router(register.router,prefix='/api/commission-documents')
    app.include_router(receipts.router,prefix='/api/receipt-commissions')
    app.include_router(mortuary.router,prefix='/api/mortuary')
    identity={'id':1}
    app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=identity['id'])
    app.dependency_overrides[get_db]=lambda:db
    return TestClient(app),identity


def partial(db,amount='500.00'):
    configure(db);quote_and_import(db,import_payload());stage_invoice(db,total='1150.00')
    result=stage_receipt(db,[dict(receipt(),gross_received=amount)],people=(11,))
    db.execute(text("UPDATE commission_documents SET created_at='2026-11-06 08:00:00'"));db.commit()
    return result['document_ids'][0]


def test_register_groups_uploads_by_month_and_branch_but_checks_all_payment_months(database):
    did=partial(database)
    database.execute(text("UPDATE commission_documents SET created_at='2026-10-31 20:00:00' WHERE kind='invoice'"));database.commit()
    client,_=client_for(database)
    result=client.get('/api/commission-documents?month=2026-11').json()
    assert result['total']==2 and {d['kind'] for d in result['documents']}=={'receipt','mortuary'}
    case=result['cases'][0]
    assert case['invoice_total']=='1150.0' or Decimal(case['invoice_total'])==Decimal('1150')
    assert case['total_received']=='500.00' and case['balance']=='650.00' and not case['ready']
    assert client.get('/api/commission-documents?month=2026-11&branch_id=102').json()['total']==0
    assert client.get('/api/commission-documents?month=2026-11&branch_id=900').status_code==403
    assert client.get('/api/commission-documents?month=2026-13').status_code==422


@pytest.mark.parametrize('external', [False, True])
def test_inactive_branch_documents_remain_browsable_but_not_payment_ready(database, external):
    did=partial(database,amount='1150.00')
    if external:
        database.execute(text("INSERT INTO external_commission_branches(branch_id,franchise_user_id,branch_key,created_by_user_id) VALUES(101,2,'EXAMPLE',1)"))
    database.execute(text('UPDATE attendance_branches SET is_active=FALSE WHERE id IN (101,900)'))
    database.commit()
    client,_=client_for(database)
    for suffix in ('', '&branch_id=101'):
        response=client.get('/api/commission-documents?month=2026-11'+suffix)
        assert response.status_code==200
        result=response.json()
        assert result['total']==3 and len(result['documents'])==3
        assert [b['id'] for b in result['branches']]==[101]
        assert not result['branches'][0]['is_active']
        assert result['cases'][0]['branch_id']==101
        assert not result['cases'][0]['ready']
        assert result['cases'][0]['reason']=='Branch is no longer linked or available.'
    assert client.get(f'/api/commission-documents/{did}').status_code==200
    assert client.get('/api/commission-documents?month=2026-11&branch_id=900').status_code==403
    from app.services.attendance_branches import branches
    from app.services.external_commissions import external_branches
    assert 101 not in {b['id'] for b in [*branches(database,2),*external_branches(database,2)]}


def test_south_african_month_boundary_is_respected(database):
    partial(database)
    database.execute(text("UPDATE commission_documents SET created_at='2026-10-31 22:30:00'"));database.commit()
    client,_=client_for(database)
    assert client.get('/api/commission-documents?month=2026-11').json()['total']==3
    assert client.get('/api/commission-documents?month=2026-10').json()['total']==0


def test_mf_folder_opens_all_months_and_one_card_never_splits_between_pages(database):
    partial(database,amount='1150.00')
    database.execute(text("UPDATE commission_documents SET created_at='2026-10-01 08:00:00' WHERE kind='invoice'"));database.commit()
    client,_=client_for(database)
    listing=client.get('/api/commission-documents?month=2026-11&limit=1').json()
    assert listing['case_total']==1 and len(listing['cases'])==1
    case=listing['cases'][0]
    assert case['ready'] and case['document_counts']=={'mortuary':1,'invoice':1,'receipt':1}
    opened=client.get('/api/commission-documents/case',params={'branch_id':101,'mf':case['mf']})
    assert opened.status_code==200
    assert {d['kind'] for d in opened.json()['documents']}=={'mortuary','invoice','receipt'}
    assert opened.json()['case']['ready']
    assert client.get('/api/commission-documents?month=2026-11&limit=1&offset=1').json()['cases']==[]
    assert client.get('/api/commission-documents/case?branch_id=900&mf=TEST-1315').status_code==403


def test_mf_folder_is_not_complete_when_unpaid_or_archived_and_checks_access(database):
    did=partial(database)
    client,identity=client_for(database)
    result=client.get('/api/commission-documents/case?branch_id=101&mf=TEST-1315').json()
    assert not result['case']['ready'] and Decimal(result['case']['balance'])==650
    client.post(f'/api/commission-documents/{did}/archive',json={'reason':'Wrong receipt'})
    result=client.get('/api/commission-documents/case?branch_id=101&mf=TEST-1315').json()
    assert len(result['documents'])==2 and not result['case']['ready']
    archived=client.get('/api/commission-documents/case?branch_id=101&mf=TEST-1315&include_deleted=true').json()
    assert len(archived['documents'])==3 and sum(bool(d['deleted_at']) for d in archived['documents'])==1
    identity['id']=12
    assert client.get('/api/commission-documents/case?branch_id=101&mf=TEST-1315').status_code==403


def test_same_mf_number_at_two_branches_has_separate_cards_and_evidence(database):
    partial(database,amount='1150.00')
    receipts.save_document(database,2,'mortuary',dict(record(),branch='EXAMPLE SOUTH'),[],1)
    database.commit()
    client,_=client_for(database)
    listing=client.get('/api/commission-documents?month=2026-11').json()
    assert listing['case_total']==2
    assert {c['branch_id'] for c in listing['cases']}=={101,102}
    home=client.get('/api/commission-documents/case?branch_id=101&mf=TEST-1315').json()
    other=client.get('/api/commission-documents/case?branch_id=102&mf=TEST-1315').json()
    assert home['case']['ready'] and len(home['documents'])==3
    assert not other['case']['ready'] and len(other['documents'])==1


def test_nominated_uploader_can_view_delete_and_restore_but_other_staff_cannot(database):
    did=partial(database);client,identity=client_for(database)
    identity['id']=11
    assert client.get(f'/api/commission-documents/{did}').status_code==403
    assign_staff(database,2,11,101,True);database.commit()
    assert client.get(f'/api/commission-documents/{did}').status_code==200
    assert client.post(f'/api/commission-documents/{did}/archive',json={'reason':'Wrong payment receipt'}).status_code==200
    assert not client.get('/api/commission-documents?month=2026-11').json()['documents'][0]['deleted_at']
    archived=client.get('/api/commission-documents?month=2026-11&include_deleted=true').json()
    assert len([d for d in archived['documents'] if d['deleted_at']])==1
    assert client.post(f'/api/commission-documents/{did}/restore',json={'reason':'Receipt verified'}).status_code==200
    log=client.get(f'/api/commission-documents/activity?document_id={did}').json()['items']
    assert {'commission_document_viewed','commission_document_deleted','commission_document_restored'} <= {r['action'] for r in log}
    assert all(r['actor_user_id']==11 for r in log if r['action'] in {'commission_document_deleted','commission_document_restored'})
    identity['id']=12
    assert client.get(f'/api/commission-documents/{did}').status_code==403
    identity['id']=11
    assert client.get(f'/api/commission-documents/{did}?franchise_user_id=99').status_code==403


def test_deleted_receipt_is_excluded_and_replacement_cannot_duplicate_an_award(database):
    did=partial(database);client,_=client_for(database)
    quote,_=calculate(database,[did])
    assert client.post(f'/api/commission-documents/{did}/archive',json={'reason':'Wrong amount on uploaded receipt'}).status_code==200
    assert client.post('/api/receipt-commissions/settle',json=quote.model_dump()).status_code==403
    result=stage_receipt(database,[dict(receipt(),gross_received='1150.00')],people=(11,))
    replacement=result['document_ids'][0]
    assert replacement!=did
    assert client.post(f'/api/commission-documents/{did}/restore',json={'reason':'Try old receipt'}).status_code==409
    payload,q=calculate(database,[replacement]);assert q['total']!='0'
    receipts.settle(payload,OWNER,database)
    again,_=calculate(database,[replacement]);assert receipts.settle(again,OWNER,database)['created']==0


def test_approved_case_blocks_delete_even_for_a_receipt_not_used_as_primary_link(database):
    did=partial(database)
    second=stage_receipt(database,[dict(receipt(),receipt_number='FINAL-PAY',gross_received='650.00')],people=(11,))['document_ids'][0]
    payload,_=calculate(database,[did,second]);receipts.settle(payload,OWNER,database)
    client,_=client_for(database)
    response=client.post(f'/api/commission-documents/{second}/archive',json={'reason':'Attempt to remove paid evidence'})
    assert response.status_code==409 and 'Head Office' in response.json()['detail']
    assert database.execute(text('SELECT deleted_at FROM commission_documents WHERE id=:id'),{'id':second}).scalar() is None
    assert client.get(f'/api/commission-documents/activity?document_id={second}').json()['items'][0]['action']=='commission_document_deletion_blocked'


def test_overpayment_blocks_commission_until_receipts_balance_invoice(database):
    did=partial(database,amount='1150.01')
    payload,q=calculate(database,[did])
    assert q['total']=='0' and all(r['state']=='blocked' for r in q['items'])
    assert 'exceed the invoice' in q['items'][0]['reason']
    assert receipts.settle(payload,OWNER,database)['created']==0


def test_reupload_cannot_change_removal_time_without_a_logged_correction(database):
    partial(database)
    with pytest.raises(HTTPException,match='different details'):
        quote_and_import(database,import_payload([dict(record(),time_in='09:00')]))
    assert json.loads(database.execute(text("SELECT source_data FROM commission_documents WHERE kind='mortuary'")).scalar())['time_in']==record()['time_in']


def test_home_permissions_inherit_and_explicit_branch_overrides_can_disable_all(database):
    configure(database)
    save_branch_options(database,2,11,{101:{'enabled_types':['removals','invoice_commission'],'rates':{'driver_out':'250','driver_invoice_commission':'4'}}},1);database.commit()
    choices=branch_options(database,2,11)
    assert choices['102']['inherit_home'] and enabled_for_branch(database,2,11,'removals',102)
    assert choices['102']['rates']['driver_out']=='250'
    choices['102']={'enabled_types':[],'inherit_home':False}
    save_branch_options(database,2,11,choices,1);database.commit()
    assert not enabled_for_branch(database,2,11,'removals',102)
    assert enabled_for_branch(database,2,11,'removals',101)
    choices=branch_options(database,2,11);choices['102']={'inherit_home':True,'enabled_types':[]}
    save_branch_options(database,2,11,choices,1);database.commit()
    assert enabled_for_branch(database,2,11,'removals',102)


def test_same_employee_earns_separate_branch_fees_and_combined_total(database):
    configure(database)
    save_branch_options(database,2,11,{101:{'enabled_types':['removals'],'rates':{'driver_out':'250'}},102:{'enabled_types':['removals'],'rates':{'driver_out':'400'}}},1)
    save_branch_options(database,2,12,{},1);database.commit()
    for name in ['EXAMPLE','EXAMPLE SOUTH']:
        quote_and_import(database,import_payload([dict(record(),branch=name)]))
        result=stage_receipt(database,[dict(receipt(),branch=name,gross_received='1150.00')],people=())
        payload,_=calculate(database,result['document_ids']);receipts.settle(payload,OWNER,database)
    a=commission.entries(employee_user_id=11,earning_branch_id=101,current_user=OWNER,db=database)
    b=commission.entries(employee_user_id=11,earning_branch_id=102,current_user=OWNER,db=database)
    assert a['total']==Decimal('250') and b['total']==Decimal('400')
    assert commission.entries(employee_user_id=11,current_user=OWNER,db=database)['total']==Decimal('650')
    assert database.execute(text('SELECT branch_id FROM employee_branch_assignments WHERE employee_user_id=11')).scalar()==101


def test_linked_branch_inherits_home_invoice_percentage_and_can_override_it(database):
    configure(database)
    save_branch_options(database,2,11,{101:{'enabled_types':['invoice_commission'],'rates':{'driver_invoice_commission':'4'}}},1)
    save_branch_options(database,2,12,{},1);database.commit()
    quote_and_import(database,import_payload([dict(record(),branch='EXAMPLE SOUTH')]))
    ids=stage_receipt(database,[dict(receipt(),branch='EXAMPLE SOUTH',gross_received='1150.00')],people=(11,))['document_ids']
    payload,q=calculate(database,ids)
    invoice=next(r for r in q['items'] if r.get('category')=='invoice_commission')
    assert invoice['amount']=='40.00' and invoice['earning_branch_id']==102 and invoice['employee_branch_id']==101
    options=branch_options(database,2,11)
    options['102']={'enabled_types':['invoice_commission'],'rates':{'driver_invoice_commission':'8'}}
    save_branch_options(database,2,11,options,1);database.commit()
    with pytest.raises(HTTPException,match='changed'):receipts.settle(payload,OWNER,database)
    _,q=calculate(database,ids)
    assert next(r for r in q['items'] if r.get('category')=='invoice_commission')['amount']=='80.00'


def test_original_pdfs_are_retained_for_all_three_types_and_views_logged(database):
    configure(database);client,_=client_for(database)
    for kind,body,path in [('invoice',INVOICE,'/api/receipt-commissions/invoices/preview'),('mortuary',SAMPLE,'/api/mortuary/preview'),('receipt',__import__('tests.test_receipt_commissions',fromlist=['RECEIPT']).RECEIPT,'/api/receipt-commissions/preview')]:
        stream=BytesIO();pdf=canvas.Canvas(stream)
        for n,line in enumerate(body.splitlines()):pdf.drawString(20,800-n*18,line)
        pdf.save();content=stream.getvalue()
        result=client.post(path,files=[('files',(kind+'.pdf',content,'application/pdf'))])
        assert result.status_code==200,result.text
        records=result.json()['records'];assert len(records)==1,result.json()
        did,_=receipts.save_document(database,2,kind,records[0],[],1);database.commit()
        assert client.get(f'/api/commission-documents/{did}/file').content==content
        assert client.get(f'/api/commission-documents/{did}/file?download=true').content==content
        actions={r['action'] for r in client.get(f'/api/commission-documents/activity?document_id={did}').json()['items']}
        assert {'commission_document_saved','commission_document_pdf_viewed','commission_document_downloaded'}<=actions

