import json
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from app.api import commission
from app.services.case_claims import removal_applicability
from app.services.commission_automation import auto_approve_holder
from app.services.receipt_commissions import save_branch_options
from tests.test_mortuary_book import database,record,import_payload,quote_and_import
from tests.test_receipt_commissions import stage_receipt
from tests.test_case_claims import setup,claim,STAFF


@pytest.mark.parametrize('manager',[False,True])
def test_claim_omits_other_peoples_removal_and_preserves_other_commissions(database,monkeypatch,manager):
    setup(database)
    if manager:
        previous=commission._profile
        monkeypatch.setattr(commission,'_profile',lambda db,user:({'ManagerUser'},2,11,11,'manager') if user.id==11 else previous(db,user))
    book=dict(record(),names=['Aubrey'],driver='Ewald',driver_in='Aubrey')
    request=import_payload([book]);request.allocations=[request.allocations[0].model_copy(update={'employee_user_id':12})]
    quote_and_import(database,request);stage_receipt(database,people=())
    result=claim(database)
    assert {item['category'] for item in result['items']}=={'invoice_commission','grave_service'}
    assert database.execute(text("SELECT COUNT(*) FROM commission_entries WHERE employee_user_id=11 AND commission_type='removals'")).scalar()==0
    assert removal_applicability(database,2,11,101,'TEST1315') is False
    assert removal_applicability(database,2,12,101,'TEST1315') is True


def test_both_driver_in_staff_can_claim_their_removal_with_correct_roles(database):
    setup(database)
    save_branch_options(database,2,12,{101:{'enabled_types':['removals'],'rates':{'assistant_out':'150','driver_out':'200'}}},1,branch_id=101)
    database.commit();quote_and_import(database,import_payload());stage_receipt(database,people=())
    first=claim(database)
    second=commission.case_claim(commission.CaseClaimIn(earning_branch_id=101,reference='TEST1315'),type(STAFF)(id=12),database)
    assert any(item['category']=='removals' for item in first['items'])
    assert second['items'][0]['category']=='removals' and second['items'][0]['amount']=='150.00'


def test_claim_before_upload_is_retired_when_book_names_another_employee(database):
    setup(database);claim(database)
    removal=database.execute(text("SELECT id FROM commission_entries WHERE commission_type='removals'")).scalar()
    book=dict(record(),names=['Aubrey'],driver='Aubrey',driver_in='Aubrey')
    request=import_payload([book]);request.allocations=[request.allocations[0].model_copy(update={'employee_user_id':12})]
    quote_and_import(database,request)
    visible=commission.entries(current_user=STAFF,db=database)
    assert all(item['commission_type']!='removals' for item in visible['items'])
    auto_approve_holder(database,2);database.commit()
    assert database.execute(text('SELECT status FROM commission_entries WHERE id=:id'),{'id':removal}).scalar()=='cancelled'
    assert database.execute(text("SELECT COUNT(*) FROM commission_entry_audit WHERE entry_id=:id AND action='removal_not_in_driver_in'"),{'id':removal}).scalar()==1
    assert claim(database)['created']==0
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar()==3


def test_missing_or_ambiguous_book_keeps_preupload_claim_waiting(database):
    setup(database)
    assert removal_applicability(database,2,11,101,'TEST1315') is None
    result=claim(database)
    assert any(item['category']=='removals' for item in result['items'])
    auto_approve_holder(database,2);database.commit()
    assert database.execute(text("SELECT status FROM commission_entries WHERE commission_type='removals'")).scalar()=='pending'


def test_removal_only_permission_explains_non_applicability_without_creating_claim(database):
    setup(database,categories=('removals',))
    book=dict(record(),names=['Aubrey'],driver='Aubrey',driver_in='Aubrey')
    request=import_payload([book]);request.allocations=[request.allocations[0].model_copy(update={'employee_user_id':12})]
    quote_and_import(database,request)
    with pytest.raises(HTTPException,match='Driver In'):claim(database)
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar()==0
