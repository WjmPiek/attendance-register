from datetime import date
from decimal import Decimal
from io import BytesIO
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import text

from app.api import receipt_commissions as api, mortuary
from app.services import attendance_branches as branch_service
from app.services.receipt_commissions import parse_receipt_text, receipt_base, set_enabled_types, branch_key, mf_key, require_manual_eligibility, printed_money, save_branch_options, branch_options, enabled_for_branch
from tests.test_mortuary_book import database, record, import_payload, quote_and_import

OWNER = SimpleNamespace(id=1)
RECEIPT = '''MARTINS FUNERALS
EXAMPLE
MARTINS EXAMPLE
Date 07-Oct-26
KWITANSIE / RECEIPT
Receipt Nr. TEST-1492
MF No. TEST-1315
Deceased: Example Person
ID Num: 0000000000000
Inv No. 1309
Bal Due: R 0.00
Amnt Rcvd: R 23580.61
Tot Amnt: R 23580.61
'''


def receipt(**changes):
    return dict(parse_receipt_text(RECEIPT), page=1, filename='receipt.pdf', source_hash='b'*64, **changes)


def configure(db, registered=True):
    db.execute(text('INSERT INTO receipt_commission_settings VALUES(2,0,:registered,:number,15,2,1,NOW())'), {'registered':registered,'number':'4000000000' if registered else None})
    db.execute(text('UPDATE attendance_branches SET vat_number=:number WHERE franchise_user_id=2'), {'number':'4000000000' if registered else None})
    for uid in (11,12):
        save_branch_options(db,2,uid,{bid:{'enabled_types':['removals','invoice_commission'],'receipt_percentage':None} for bid in (101,102)},1)
    db.execute(text("UPDATE employee_commission_options SET rate=3 WHERE employee_user_id=12 AND commission_type='invoice_commission'"))
    db.commit()


def test_import_auto_detects_linked_branch_and_rejects_wrong_selection(database):
    assert api.check_import_branch(database,2,record())==101
    assert api.check_import_branch(database,2,record(),expected_branch_id=101)==101
    with pytest.raises(HTTPException) as error:
        api.check_import_branch(database,2,record(),expected_branch_id=102)
    assert error.value.status_code==400 and 'does not match selected branch' in error.value.detail
    with pytest.raises(HTTPException) as error:
        api.check_import_branch(database,2,record(),expected_branch_id=9999)
    assert error.value.status_code==403


def test_receipt_suggestions_require_matching_book_and_enabled_branch_permission(database):
    configure(database)
    source=dict(receipt(),earning_branch_id=101)
    assert api.suggest_receipt_allocations(database,2,[source],OWNER)[0]['employee_user_ids']==[]
    quote_and_import(database,import_payload())
    suggested=api.suggest_receipt_allocations(database,2,[source],OWNER)[0]
    assert set(suggested['employee_user_ids'])=={11,12}
    assert suggested['employee_roles']=={11:'driver',12:'assistant'}
    for change in [{'reference':'OTHER'},{'id_number':'1111111111111'},{'deceased':'Different Person'},{'branch':'OTHER'}]:
        assert api.suggest_receipt_allocations(database,2,[dict(source,**change)],OWNER)[0]['employee_user_ids']==[]
    save_branch_options(database,2,11,{101:{'enabled_types':['removals']}},1)
    assert api.suggest_receipt_allocations(database,2,[source],OWNER)[0]['employee_user_ids']==[12]


def stage_invoice(db, source=None, total=None):
    source = source or receipt()
    invoice = {**source, 'invoice_total': str(total if total is not None else source['gross_received'])}
    bid = api.require_branch(db, 2, source['branch'])
    tax = api.receipt_settings(db, 2, bid)
    base = receipt_base(invoice['invoice_total'], tax['vat_registered'], tax['vat_rate']) if tax['vat_registered'] is not None else None
    invoice.update(vat_registered=tax['vat_registered'], vat_number=tax.get('vat_number'), vat_rate=str(tax['vat_rate']),
                   commission_base=str(base) if base is not None else None, vat_amount=str(Decimal(invoice['invoice_total']) - base) if base is not None else None,
                   vat_issue=None if base is not None else 'Unclear printed VAT')
    return api.save_document(db, 2, 'invoice', invoice, [], 1)[0]


def stage_receipt(db, records=None, people=(11,12), with_invoice=True):
    records=records or [receipt()]
    if with_invoice:
        for row in records:
            exists = db.execute(text("SELECT id FROM commission_documents WHERE kind='invoice' AND franchise_user_id=2 AND branch_key=:branch AND mf_key=:mf"), {'branch': branch_key(row['branch']), 'mf': mf_key(row['reference'])}).scalar()
            if not exists and db.execute(text('SELECT 1 FROM attendance_branches WHERE franchise_user_id=2 AND name=:name'), {'name': row['branch']}).scalar():
                stage_invoice(db, row)
    token=api.signer().dumps({'kind':'receipts','user_id':1,'franchise_user_id':2,'records':records})
    return api.stage(api.StageIn(preview_token=token,confirmed_franchise=True,allocations=[{'record':i,'employee_user_ids':list(people)} for i in range(len(records))]),OWNER,db)


def calculate(db, ids):
    payload=api.CalculateIn(document_ids=ids)
    q=api.calculate(payload,OWNER,db)
    payload.quote_token=q['quote_token']
    return payload,q


def stage_both(db):
    quote_and_import(db,import_payload())
    result=stage_receipt(db)
    return result['document_ids']


def test_receipt_parser_separates_mf_invoice_receipt_and_payment():
    r=receipt()
    assert r['reference']=='TEST-1315'
    assert r['receipt_number']=='TEST-1492'
    assert r['invoice_number']=='1309'
    assert r['service_date']=='2026-10-07'
    assert r['gross_received']=='23580.61'
    assert r['deceased']=='Example Person'
    assert r['branch']=='EXAMPLE'
    assert mf_key('MF111098')==mf_key('111098')
    assert branch_key('MARTINS FUNERALS Northcliff (F)')=='northcliff'


def test_vat_extraction_uses_inclusive_divisor_and_nonregistered_full_payment():
    assert receipt_base('23580.61',True,15)==Decimal('20504.88')
    assert receipt_base('23580.61',False,15)==Decimal('23580.61')
    with pytest.raises(ValueError,match='Confirm'):
        receipt_base('115',None,15)
    assert printed_money('23,580.61')==Decimal('23580.61')
    assert printed_money('23 580,61')==Decimal('23580.61')
    with pytest.raises(ValueError):printed_money('23,58.061')


def test_different_mf_numbers_never_earn_any_commission(database):
    configure(database)
    quote_and_import(database,import_payload())
    result=stage_receipt(database,[dict(receipt(),reference='MF111098')])
    _,q=calculate(database,result['document_ids'])
    assert all(row['state']=='blocked' for row in q['items'])
    assert q['total']=='0'
    payload,_=calculate(database,[r['id'] for r in database.execute(text('SELECT id FROM commission_documents')).mappings()])
    assert api.settle(payload,OWNER,database)['created']==0
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar()==0


def test_paired_docs_create_separate_categories_cross_branch_staff_and_totals(database):
    configure(database)
    ids=stage_both(database)
    payload,q=calculate(database,ids)
    assert len(q['items'])==4 and all(r['state']=='ready' for r in q['items'])
    assert {r['employee_branch_name'] for r in q['items']}=={'EXAMPLE','EXAMPLE SOUTH'}
    assert api.settle(payload,OWNER,database)['created']==4
    rows=database.execute(text('SELECT * FROM commission_entries')).mappings().all()
    amounts={(r['employee_user_id'],r['commission_type']):Decimal(str(r['calculated_amount'])) for r in rows}
    assert amounts[(11,'removals')]==Decimal('200')
    assert amounts[(12,'removals')]==Decimal('150')
    assert amounts[(11,'invoice_commission')]==Decimal('410.10')
    assert amounts[(12,'invoice_commission')]==Decimal('615.15')
    assert all(r['status']=='approved' and r['quantity']==1 for r in rows)
    invoice=next(r for r in rows if r['commission_type']=='invoice_commission')
    assert Decimal(str(invoice['invoice_value_before_tax']))==Decimal('20504.88')
    assert 'Example Person' in invoice['notes'] and '0000000000000' in invoice['notes']
    assert 'TEST-1315' in invoice['reference'] and '1309' in invoice['reference']
    # Both import stages and approval are repeat-safe.
    stage_receipt(database)
    quote_and_import(database,import_payload())
    again,_=calculate(database,ids)
    assert api.settle(again,OWNER,database)['created']==0


def test_receipt_can_arrive_first_and_nonregistered_receipts_use_full_payment(database):
    configure(database,False)
    result=stage_receipt(database)
    _,q=calculate(database,result['document_ids'])
    assert all(r['state']=='blocked' for r in q['items'])
    quote_and_import(database,import_payload())
    payload,q=calculate(database,result['document_ids'])
    invoices=[r for r in q['items'] if r.get('category')=='invoice_commission']
    assert all(r['base_amount']=='23580.61' for r in invoices)
    assert next(r for r in invoices if r['employee_user_id']==11)['amount']=='471.61'
    assert api.settle(payload,OWNER,database)['created']==4


def test_disabled_categories_stay_blocked_but_branch_vat_can_resolve_invoice(database):
    configure(database)
    ids=stage_both(database)
    database.execute(text("UPDATE employee_commission_options SET enabled=FALSE WHERE employee_user_id=11 AND commission_type='removals'"))
    database.execute(text('DELETE FROM receipt_commission_settings'));database.commit()
    payload,q=calculate(database,ids)
    assert sum(r['state']=='ready' for r in q['items'])==2
    assert api.settle(payload,OWNER,database)['created']==2
    assert database.execute(text("SELECT COUNT(*) FROM commission_entries WHERE commission_type='invoice_commission'")).scalar()==1


def test_receipt_recipient_must_be_enabled_and_belong_to_holder(database):
    configure(database)
    with pytest.raises(HTTPException):
        stage_receipt(database,people=(99,))
    database.execute(text("UPDATE employee_commission_options SET enabled=FALSE WHERE employee_user_id=11 AND commission_type='invoice_commission'"));database.commit()
    with pytest.raises(HTTPException,match='enabled'):
        stage_receipt(database,people=(11,))


def test_matching_mf_with_conflicting_deceased_id_is_blocked(database):
    configure(database)
    quote_and_import(database,import_payload())
    result=stage_receipt(database,[dict(receipt(),id_number='1111111111111')])
    payload,q=calculate(database,result['document_ids'])
    assert all(r['state']=='blocked' for r in q['items'])
    assert api.settle(payload,OWNER,database)['created']==0


def test_same_mf_under_another_branch_does_not_match(database):
    configure(database)
    quote_and_import(database,import_payload())
    result=stage_receipt(database,[dict(receipt(),branch='EXAMPLE SOUTH')])
    _,q=calculate(database,result['document_ids'])
    assert all(r['state']=='blocked' for r in q['items'])
    with pytest.raises(HTTPException,match='does not match'):
        stage_receipt(database,[dict(receipt(),branch='FOREIGN')])


def test_same_receipt_with_changed_payment_is_rejected(database):
    configure(database)
    stage_receipt(database)
    with pytest.raises(HTTPException,match='different details'):
        stage_receipt(database,[dict(receipt(),gross_received='99999.00')])


def test_additional_payment_does_not_award_the_same_invoice_twice(database):
    configure(database)
    ids=stage_both(database)
    payload,_=calculate(database,ids);api.settle(payload,OWNER,database)
    result=stage_receipt(database,[dict(receipt(),receipt_number='TEST-1493',gross_received='1150.00')])
    payload,_=calculate(database,result['document_ids'])
    assert api.settle(payload,OWNER,database)['created']==0
    assert database.execute(text("SELECT COUNT(*) FROM commission_entries WHERE commission_type='removals'")).scalar()==2


def test_changed_employee_optin_or_rate_invalidates_quote(database):
    configure(database)
    payload,_=calculate(database,stage_both(database))
    database.execute(text("UPDATE employee_commission_options SET rate=4 WHERE employee_user_id=12 AND commission_type='invoice_commission'"));database.commit()
    with pytest.raises(HTTPException,match='changed'):
        api.settle(payload,OWNER,database)
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar()==0


def test_failed_award_batch_rolls_back_every_entry(database,monkeypatch):
    configure(database);payload,_=calculate(database,stage_both(database))
    calls=[]
    def fail(*args,**kwargs):
        calls.append(True)
        if len(calls)==2:raise RuntimeError('Failure')
    monkeypatch.setattr(api,'_notify',fail)
    with pytest.raises(RuntimeError):api.settle(payload,OWNER,database)
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar()==0


def test_selected_importer_can_allocate_group_staff_but_other_staff_cannot(database):
    with pytest.raises(HTTPException):branch_service.import_scope(database,SimpleNamespace(id=11))
    branch_service.assign_staff(database,2,11,101,True);database.commit()
    assert branch_service.import_scope(database,SimpleNamespace(id=11))==2
    assert {p['user_id'] for p in branch_service.import_staff(database,2)}=={11,12}
    assert branch_service.import_participant(database,SimpleNamespace(id=11),12,2)['branch_name']=='EXAMPLE SOUTH'
    with pytest.raises(HTTPException):branch_service.import_scope(database,SimpleNamespace(id=11),99)
    with pytest.raises(HTTPException):branch_service.import_participant(database,SimpleNamespace(id=11),99,2)


def test_branch_sync_preserves_employee_assignment_and_deactivates_unlinked_branch(database):
    branch_service.sync_branches(database,2,[{'id':1,'name':'Example'},{'id':3,'name':'New Branch'}]);database.commit()
    assert branch_service.assignment(database,11)['branch_id']==101
    assert branch_service.assignment(database,12)['branch_active']==False
    assert {b['name'] for b in branch_service.branches(database,2)}=={'Example','New Branch'}
    with pytest.raises(HTTPException):branch_service.assign_staff(database,2,11,900,False)


def test_manual_entry_cannot_bypass_document_pairing_or_employee_optin(database):
    person={'franchise_user_id':2,'user_id':11}
    with pytest.raises(HTTPException,match='not enabled'):require_manual_eligibility(database,person,'joinings')
    configure(database)
    for category in ('removals','invoice_commission'):
        with pytest.raises(HTTPException,match='matched'):require_manual_eligibility(database,person,category)


def test_branch_and_individual_pdfs_contain_only_selected_employee_totals(database):
    configure(database);payload,_=calculate(database,stage_both(database));api.settle(payload,OWNER,database)
    import asyncio
    async def contents(response):
        return b''.join([part async for part in response.body_iterator])
    response=api.report('2026-10',branch_id=101,employee_user_id=12,current_user=OWNER,db=database)
    result=asyncio.run(contents(response))
    text_content='\n'.join(p.extract_text() for p in PdfReader(BytesIO(result)).pages)
    assert 'Aubrey Example' in text_content and 'Ewald Example' not in text_content
    assert 'MF File Receipts subtotal: R 615.15' in text_content
    assert 'EXAMPLE' in text_content and 'TEST-1492' in text_content
    with pytest.raises(HTTPException):api.report('2026-10',branch_id=900,current_user=OWNER,db=database)


def test_twenty_matched_files_pay_eighty_separate_category_entries(database):
    configure(database)
    books=[dict(record(),reference=f'TEST-{i}') for i in range(20)]
    quote_and_import(database,import_payload(books))
    receipts=[dict(receipt(),reference=f'TEST-{i}',invoice_number=f'INV-{i}',receipt_number=f'PAY-{i}',gross_received='1150.00') for i in range(20)]
    result=stage_receipt(database,receipts)
    payload,q=calculate(database,result['document_ids'])
    assert len(q['items'])==80
    assert api.settle(payload,OWNER,database)['created']==80
    assert database.execute(text('SELECT SUM(calculated_amount) FROM commission_entries WHERE employee_user_id=11')).scalar()==4400
    assert database.execute(text('SELECT SUM(calculated_amount) FROM commission_entries WHERE employee_user_id=12')).scalar()==3600


def test_system_branch_vat_registration_resolves_unclear_invoice(database):
    configure(database)
    database.execute(text("UPDATE attendance_branches SET vat_number='4000000001' WHERE id=102"));database.commit()
    quote_and_import(database,import_payload([dict(record(),branch='EXAMPLE SOUTH')]))
    result=stage_receipt(database,[dict(receipt(),branch='EXAMPLE SOUTH')])
    _,q=calculate(database,result['document_ids'])
    assert all(r['state']=='ready' and r['vat_source']=='System branch VAT registration' and r['base_amount']=='20504.88' for r in q['items'] if r['category']=='invoice_commission')
    api.save_settings(api.SettingsIn(branch_id=102,vat_registered=False,receipt_percentage=None),OWNER,database)
    _,q=calculate(database,result['document_ids'])
    assert all(r['base_amount']=='20504.88' and r['state']=='ready' for r in q['items'] if r['category']=='invoice_commission')


def test_http_import_delegate_cannot_change_rates_or_print_group_reports(database):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user
    from app.db.session import get_db
    app=FastAPI();app.include_router(api.router,prefix='/api/receipt-commissions')
    user={'id':1}
    app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=user['id'])
    app.dependency_overrides[get_db]=lambda:database
    client=TestClient(app)
    configure(database)
    assert client.get('/api/receipt-commissions/branches').status_code==200
    assert client.get('/api/receipt-commissions/options/11').json()['assignment']['branch_id']==101
    user['id']=11
    assert client.get('/api/receipt-commissions/settings').status_code==403
    branch_service.assign_staff(database,2,11,101,True);database.commit()
    assert client.get('/api/receipt-commissions/settings').status_code==200
    assert len(client.get('/api/receipt-commissions/settings').json()['employees'])==2
    assert client.put('/api/receipt-commissions/settings',json={'vat_registered':False}).status_code==403
    assert client.get('/api/receipt-commissions/report.pdf?month=2026-10').status_code==403
    assert client.get('/api/receipt-commissions/options/12').status_code==403


def test_three_branches_only_registered_branch_excludes_vat(database):
    configure(database,False)
    database.execute(text("INSERT INTO attendance_branches VALUES(103,2,3,'EXAMPLE WEST',NULL,TRUE,TRUE)"));database.commit()
    for uid in (11,12):
        save_branch_options(database,2,uid,{bid:{'enabled_types':['removals','invoice_commission'],'receipt_percentage':None} for bid in (101,102,103)},1)
    database.commit()
    api.save_settings(api.SettingsIn(branch_id=101,vat_registered=True,vat_number='4000000000',receipt_percentage=2),OWNER,database)
    for bid in (102,103):api.save_settings(api.SettingsIn(branch_id=bid,vat_registered=False,receipt_percentage=2),OWNER,database)
    names=['EXAMPLE','EXAMPLE SOUTH','EXAMPLE WEST']
    quote_and_import(database,import_payload([dict(record(),branch=name) for name in names]))
    result=stage_receipt(database,[dict(receipt(),branch=name) for name in names],people=(11,))
    payload,q=calculate(database,result['document_ids'])
    invoices={r['branch']:r for r in q['items'] if r.get('category')=='invoice_commission'}
    assert invoices['EXAMPLE']['base_amount']=='20504.88'
    assert invoices['EXAMPLE']['amount']=='410.10'
    for name in names[1:]:
        assert invoices[name]['base_amount']=='23580.61'
        assert invoices[name]['amount']=='471.61'
    assert api.settle(payload,OWNER,database)['created']==9


def test_group_branch_with_blank_vat_number_never_silently_inherits_registered_status(database):
    configure(database)
    database.execute(text('UPDATE attendance_branches SET vat_number=NULL WHERE id=101'));database.commit()
    _,q=calculate(database,stage_both(database))
    assert all(r['state']=='blocked' for r in q['items'] if r.get('category')=='invoice_commission')
