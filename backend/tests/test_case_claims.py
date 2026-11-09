import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text

from app.api import commission
from app.services.receipt_commissions import save_branch_options
from tests.test_mortuary_book import database, record, import_payload, quote_and_import
from tests.test_receipt_commissions import configure, receipt, stage_receipt

STAFF = SimpleNamespace(id=11)


def setup(db, categories=('removals','invoice_commission','grave_service')):
    configure(db)
    save_branch_options(db,2,11,{101:{'enabled_types':list(categories),'rates':{
        'driver_grave_service':'75','assistant_grave_service':'45','driver_invoice_commission':'2',
        'assistant_invoice_commission':'1','driver_out':'200','assistant_out':'150'}}},1)
    save_branch_options(db,2,12,{},1)
    db.commit()


def evidence(db, branch='EXAMPLE', **changes):
    quote_and_import(db,import_payload([dict(record(),branch=branch)]))
    return stage_receipt(db,[dict(receipt(),branch=branch,**changes)],people=())


def claim(db, branch=101, reference='MF TEST-1315', **changes):
    return commission.case_claim(commission.CaseClaimIn(earning_branch_id=branch,reference=reference,**changes),STAFF,db)


@pytest.mark.parametrize('manager',[False,True])
def test_staff_enter_only_mf_and_branch_and_all_enabled_items_wait_for_finalisation(database,monkeypatch,manager):
    setup(database)
    if manager:
        database.execute(text('DELETE FROM employee_users WHERE user_id=11'))
        database.execute(text("INSERT INTO manager_users(id,user_id,franchise_user_id,name,surname,employee_number,is_active) VALUES(11,11,2,'Ewald','Example','11',TRUE)"))
        previous=commission._profile
        monkeypatch.setattr(commission,'_profile',lambda db,user: ({'ManagerUser'},2,11,11,'manager') if user.id==11 else previous(db,user))
        database.commit()
    evidence(database)
    result=claim(database)
    assert result['status']=='pending' and result['created']==3
    assert {row['category'] for row in result['items']}=={'removals','invoice_commission','grave_service'}
    assert Decimal(result['total'])==Decimal('685.10')
    rows=database.execute(text('SELECT * FROM commission_entries ORDER BY id')).mappings().all()
    assert all(row['employee_user_id']==11 and row['earning_branch_id']==101 and row['status']=='pending' for row in rows)
    removal=next(row for row in rows if row['commission_type']=='removals')
    assert str(removal['service_date'])=='2026-10-25'
    assert json.loads(removal['source_metadata'])['claim_deceased']=='Example Person'


def test_linked_branch_uses_its_own_exclusions_and_rates(database):
    setup(database)
    save_branch_options(database,2,11,{102:{'enabled_types':['invoice_commission'],'rates':{'driver_invoice_commission':'5'}}},1,branch_id=102)
    database.commit();evidence(database,'EXAMPLE SOUTH')
    result=claim(database,102)
    assert result['created']==1 and result['total']=='1025.24'
    assert result['items'][0]['category']=='invoice_commission'
    assert database.execute(text("SELECT COUNT(*) FROM commission_entries WHERE commission_type='removals'")).scalar()==0


@pytest.mark.parametrize('stage',['none','book','partial','mismatch'])
def test_missing_unpaid_or_mismatched_evidence_saves_waiting_without_approval(database,stage):
    setup(database)
    if stage=='book':quote_and_import(database,import_payload())
    if stage=='partial':
        from tests.test_receipt_commissions import stage_invoice
        quote_and_import(database,import_payload());stage_invoice(database,total='23580.61')
        stage_receipt(database,[dict(receipt(),gross_received='100')],people=())
    if stage=='mismatch':evidence(database,deceased='Different Person')
    result=claim(database)
    assert result['status']=='pending' and result['created']==3 and result['notice']
    assert set(database.execute(text('SELECT status FROM commission_entries')).scalars())=={'pending'}
    from app.services.commission_automation import auto_approve_holder
    auto_approve_holder(database,2);database.commit()
    assert database.execute(text("SELECT COUNT(*) FROM commission_entries WHERE status='approved'")).scalar()==0


def test_repeat_and_differently_formatted_mf_do_not_duplicate_commissions(database):
    setup(database);evidence(database)
    first=claim(database)
    second=claim(database,reference='TEST1315')
    assert first['created']==3 and second['created']==0 and second['new_total']=='0.00' and second['waiting_total']=='685.10'
    assert all(row['state']=='existing' for row in second['items'])
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar()==3


def test_claimant_cannot_submit_for_another_employee_or_foreign_branch(database):
    setup(database);evidence(database)
    result=claim(database,employee_user_id=12)
    assert result['created']==3
    assert database.execute(text('SELECT DISTINCT employee_user_id FROM commission_entries')).scalars().all()==[11]
    with pytest.raises(HTTPException,match='outside'):
        claim(database,900)


def test_disabled_categories_and_zero_rates_are_respected(database):
    setup(database,categories=('grave_service',))
    save_branch_options(database,2,11,{101:{'enabled_types':['grave_service'],'rates':{'driver_grave_service':'0'}}},1)
    database.commit();evidence(database)
    result=claim(database)
    assert result['created']==1 and result['total']=='0.00' and result['items'][0]['category']=='grave_service'
    save_branch_options(database,2,11,{101:{'enabled_types':[]}},1);database.commit()
    with pytest.raises(HTTPException,match='No commission'):
        claim(database)


def test_printed_removal_role_is_inferred_and_other_peoples_removal_cannot_be_claimed(database):
    setup(database)
    book=dict(record(),names=['Aubrey','Ewald'],driver='Aubrey',driver_in='Aubrey and Ewald')
    quote_and_import(database,import_payload([book]));stage_receipt(database,people=())
    result=claim(database)
    assert next(row for row in result['items'] if row['category']=='removals')['amount']=='150.00'
    assert next(row for row in result['items'] if row['category']=='grave_service')['amount']=='45.00'


def test_staff_not_named_under_driver_in_receive_only_other_enabled_fees(database):
    setup(database)
    book=dict(record(),names=['Aubrey'],driver='Aubrey',driver_in='Aubrey')
    request=import_payload([book])
    request.allocations=[request.allocations[0].model_copy(update={'employee_user_id':12})]
    quote_and_import(database,request);stage_receipt(database,people=())
    result=claim(database)
    assert result['created']==2
    assert all(row['category']!='removals' for row in result['items'])
    from app.services.commission_automation import auto_approve_holder
    auto_approve_holder(database,2);database.commit()
    assert database.execute(text("SELECT COUNT(*) FROM commission_entries WHERE commission_type='removals' AND status='approved'")).scalar()==0


@pytest.mark.parametrize('values',[{'rate_override':999},{'commission_type':'joinings'},{'claim_deceased':'Someone'},{'commission_role':'assistant'},{'service_date':'2026-11-09'}])
def test_case_request_cannot_supply_prices_categories_identity_or_dates(values):
    with pytest.raises(ValidationError):
        commission.CaseClaimIn(earning_branch_id=101,reference='TEST1315',**values)


def test_case_allocation_is_atomic_when_a_later_write_fails(database,monkeypatch):
    setup(database);evidence(database)
    save=commission._save_claim_entry
    def fail(db,user,participant,payload,quote,**options):
        if payload.commission_type=='invoice_commission':raise RuntimeError('simulated write failure')
        return save(db,user,participant,payload,quote,**options)
    monkeypatch.setattr(commission,'_save_claim_entry',fail)
    with pytest.raises(RuntimeError):claim(database)
    database.rollback()
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar()==0


def test_outside_branch_fee_is_added_only_once_for_all_enabled_services(database):
    from app.api import receipt_commissions as api
    from tests.test_receipt_commissions import OWNER
    from tests.test_service_claims import outside_evidence
    setup(database,categories=('grave_service','church_service','service_other_branch'))
    save_branch_options(database,2,11,{101:{'enabled_types':['grave_service','church_service','service_other_branch'],
        'rates':{'driver_grave_service':'75','driver_church_service':'60','driver_other_branch':'50'}}},1)
    database.commit()
    branch=api.declare_external_branch(api.ExternalBranchIn(name='OUTSIDE',vat_number='4000000000'),OWNER,database)
    outside_evidence(database,branch['id'])
    result=claim(database,branch['id'])
    assert result['created']==2 and result['total']=='135.00'
    from app.services.commission_automation import auto_approve_holder
    auto_approve_holder(database,2);database.commit()
    assert database.execute(text("SELECT COUNT(*) FROM commission_entries WHERE commission_type='service_other_branch'")).scalar()==1
    assert claim(database,branch['id'])['created']==0


def test_rejected_commissions_are_not_approved_again_by_resubmitting_the_mf(database):
    setup(database);evidence(database);claim(database)
    database.execute(text("UPDATE commission_entries SET status='rejected'"));database.commit()
    result=claim(database)
    assert result['created']==0 and all(row['status']=='rejected' for row in result['items'])


def test_missing_rate_blocks_only_that_enabled_item(database):
    setup(database,categories=('grave_service','joinings'))
    database.execute(text('CREATE TABLE commission_structures(id INTEGER PRIMARY KEY,franchise_user_id INT,commission_type TEXT,rate NUMERIC,is_active BOOLEAN)'))
    database.commit();evidence(database)
    result=claim(database)
    assert result['created']==2 and result['total']=='75.00'
    assert next(row for row in result['items'] if row['category']=='joinings')['estimate_available'] is False


def test_claim_without_documents_appears_waiting_then_only_moves_after_finalisation(database):
    from app.services.receipt_commissions import payment_eligibility
    from app.services.commission_automation import auto_approve_holder
    setup(database)
    result=claim(database)
    assert result['created']==3 and result['total']=='75.00'
    rows=database.execute(text('SELECT * FROM commission_entries')).mappings().all()
    checks={row['commission_type']:payment_eligibility(database,row) for row in rows}
    assert checks['grave_service']['expected_amount']=='75.00'
    assert checks['invoice_commission']['estimate_available'] is False
    auto_approve_holder(database,2);database.commit()
    assert set(database.execute(text('SELECT status FROM commission_entries')).scalars())=={'pending'}
    evidence(database)
    assert set(database.execute(text('SELECT status FROM commission_entries')).scalars())=={'pending'}
    auto_approve_holder(database,2);database.commit()
    assert set(database.execute(text('SELECT status FROM commission_entries')).scalars())=={'approved'}
    assert sum(database.execute(text('SELECT calculated_amount FROM commission_entries')).scalars())==pytest.approx(685.10)
