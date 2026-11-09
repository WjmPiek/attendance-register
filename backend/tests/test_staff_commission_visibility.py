import pytest
from fastapi import HTTPException
from sqlalchemy import text
from app.api import commission,receipt_commissions as api
from app.services.receipt_commissions import save_branch_options
from tests.test_mortuary_book import database
from tests.test_case_claims import setup,evidence,claim,STAFF
from tests.test_receipt_commissions import OWNER


@pytest.mark.parametrize('manager',[False,True])
def test_staff_lists_totals_and_details_hide_disabled_items_but_owner_retains_ledger(database,monkeypatch,manager):
    setup(database);evidence(database);claim(database)
    if manager:
        previous=commission._profile
        monkeypatch.setattr(commission,'_profile',lambda db,user:({'ManagerUser'},2,11,11,'manager') if user.id==11 else previous(db,user))
    grave=database.execute(text("SELECT id FROM commission_entries WHERE commission_type='grave_service'")).scalar()
    save_branch_options(database,2,11,{102:{'enabled_types':['grave_service']}},1,branch_id=102)
    save_branch_options(database,2,11,{101:{'enabled_types':['invoice_commission']}},1,branch_id=101)
    database.commit()
    result=commission.entries(current_user=STAFF,db=database)
    assert {row['commission_type'] for row in result['items']}=={'invoice_commission'}
    assert {row['commission_type'] for row in result['branch_category_totals']}=={'invoice_commission'}
    assert sum(result['counts'].values())==1
    with pytest.raises(HTTPException) as exc:
        commission.entry_detail(grave,current_user=STAFF,db=database)
    assert exc.value.status_code==404
    assert len(commission.entries(employee_user_id=11,current_user=OWNER,db=database)['items'])==3
    save_branch_options(database,2,11,{101:{'enabled_types':[]}},1,branch_id=101);database.commit()
    empty=commission.entries(current_user=STAFF,db=database)
    assert empty['items']==empty['pending_imports']==empty['branch_category_totals']==[]
    assert empty['total']==0 and all(value==0 for value in empty['counts'].values())
    with pytest.raises(HTTPException,match='No commission'):
        claim(database)
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar()==3
    save_branch_options(database,2,11,{101:{'enabled_types':['grave_service'],'rates':{'driver_grave_service':'75'}}},1,branch_id=101);database.commit()
    assert [row['id'] for row in commission.entries(current_user=STAFF,db=database)['items']]==[grave]


def test_approved_totals_follow_current_permissions_without_changing_saved_amounts(database):
    from app.services.commission_automation import auto_approve_holder
    setup(database);evidence(database);claim(database)
    auto_approve_holder(database,2);database.commit()
    before=database.execute(text('SELECT SUM(calculated_amount) FROM commission_entries')).scalar()
    save_branch_options(database,2,11,{101:{'enabled_types':['grave_service']}},1,branch_id=101);database.commit()
    result=commission.entries(current_user=STAFF,db=database)
    assert result['total']==75 and result['counts']['approved']==1
    assert database.execute(text('SELECT SUM(calculated_amount) FROM commission_entries')).scalar()==before


def test_global_disable_and_inactive_branch_hide_document_estimates_as_well_as_entries(database):
    setup(database);evidence(database)
    assert commission.entries(current_user=STAFF,db=database)['pending_imports']
    database.execute(text('UPDATE employee_commission_options SET enabled=FALSE WHERE employee_user_id=11'));database.commit()
    result=commission.entries(current_user=STAFF,db=database)
    assert result['items']==result['pending_imports']==[]
    database.execute(text('UPDATE employee_commission_options SET enabled=TRUE WHERE employee_user_id=11'))
    database.execute(text('UPDATE attendance_branches SET is_active=FALSE WHERE id=101'));database.commit()
    result=commission.entries(current_user=STAFF,db=database)
    assert result['items']==result['pending_imports']==[]


def test_outside_branch_visibility_uses_enabled_home_permissions(database):
    setup(database,categories=('grave_service',))
    branch=api.declare_external_branch(api.ExternalBranchIn(name='OUTSIDE',vat_number='4000000000'),OWNER,database)
    rows=[{'franchise_user_id':2,'employee_user_id':11,'earning_branch_id':branch['id'],'commission_type':category} for category in ('grave_service','removals')]
    assert [row['commission_type'] for row in commission._staff_enabled_rows(database,STAFF,rows)]==['grave_service']
