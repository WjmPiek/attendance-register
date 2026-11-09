from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from app.api import commission,mortuary
from app.services.case_claims import quote_case_item
from app.services.mortuary import DEFAULT_WEEK
from app.services.receipt_commissions import save_branch_options,effective_branch_rates,invoice_commission_rate
from tests.test_mortuary_book import database,record,import_payload,quote_and_import
from tests.test_case_claims import setup,claim
from tests.test_receipt_commissions import OWNER


def save(db,bid,**rates):
    return mortuary.save_settings(mortuary.SavePolicy(week=DEFAULT_WEEK,rates=rates,branch_id=bid),OWNER,db)


@pytest.mark.parametrize('manager',[False,True])
def test_same_staff_uses_each_earning_branchs_fees_and_permissions(database,monkeypatch,manager):
    setup(database)
    if manager:
        previous=commission._profile
        monkeypatch.setattr(commission,'_profile',lambda db,user:({'ManagerUser'},2,11,11,'manager') if user.id==11 else previous(db,user))
    save_branch_options(database,2,11,{101:{'enabled_types':['removals','invoice_commission','grave_service']},102:{'inherit_home':True}},1)
    save_branch_options(database,2,12,{101:{'enabled_types':['removals']},102:{'enabled_types':['removals']}},1)
    database.commit()
    save(database,101,driver_sunday_holiday='250',assistant_sunday_holiday='125',driver_grave_service='50',driver_invoice_commission='2')
    save(database,102,driver_sunday_holiday='500',assistant_sunday_holiday='250',driver_grave_service='80',driver_invoice_commission='5')
    for bid,name,digest,employee,assistant,service,percent in [(101,'EXAMPLE','a',250,125,50,2),(102,'EXAMPLE SOUTH','c',500,250,80,5)]:
        quote_and_import(database,import_payload([dict(record(),branch=name,source_hash=digest*64)]))
        for uid,amount in [(11,employee),(12,assistant)]:
            _,quote=quote_case_item(database,{'franchise_user_id':2,'user_id':uid},bid,'TEST1315','removals')
            assert Decimal(quote['amount'])==amount
        _,quote=quote_case_item(database,{'franchise_user_id':2,'user_id':11},bid,'TEST1315','grave_service')
        assert Decimal(quote['amount'])==service
        assert Decimal(str(invoice_commission_rate(database,2,11,'driver',bid,mortuary.policy_map(database,2),{})))==percent
    save_branch_options(database,2,11,{102:{'enabled_types':['invoice_commission']}},1,branch_id=102);database.commit()
    result=claim(database,102)
    assert {item['category'] for item in result['items']}=={'invoice_commission'}
    assert effective_branch_rates(database,2,11,101)['driver_sunday_holiday']=='250'


def test_branch_save_is_isolated_and_blank_values_restore_main_fallback(database):
    setup(database)
    before=database.execute(text('SELECT policy FROM mortuary_policies WHERE franchise_user_id=2 AND employee_user_id=0')).scalar()
    save(database,101,driver_out='111')
    save(database,102,driver_out='222')
    save(database,102,driver_out='333')
    rows=dict(database.execute(text('SELECT branch_id,rates FROM commission_branch_rates WHERE franchise_user_id=2')).all())
    assert '111' in rows[101] and '333' in rows[102]
    assert database.execute(text('SELECT policy FROM mortuary_policies WHERE franchise_user_id=2 AND employee_user_id=0')).scalar()==before
    data=mortuary.get_settings(current_user=OWNER,db=database,branch_id=102)
    assert Decimal(data['branch_rates']['driver_out'])==333 and Decimal(data['default']['rates']['driver_out'])==333
    save(database,102,driver_out=None)
    assert mortuary.get_settings(current_user=OWNER,db=database,branch_id=102)['branch_rates']=={}
    assert '111' in database.execute(text('SELECT rates FROM commission_branch_rates WHERE branch_id=101')).scalar()


def test_individual_branch_override_takes_priority_over_branch_default(database):
    setup(database)
    save(database,101,driver_out='100')
    save(database,102,driver_out='300')
    # The existing personal home fee is the fallback; the target branch default wins.
    assert effective_branch_rates(database,2,11,101)['driver_out']=='200'
    assert Decimal(effective_branch_rates(database,2,11,102)['driver_out'])==300
    save_branch_options(database,2,11,{102:{'enabled_types':['removals'],'rates':{'driver_out':'450'}}},1,branch_id=102);database.commit()
    assert effective_branch_rates(database,2,11,102)['driver_out']=='450'


def test_foreign_inactive_and_individual_scope_cannot_change_branch_defaults(database):
    setup(database)
    for bid in (900,999):
        with pytest.raises(HTTPException):save(database,bid,driver_out='100')
    database.execute(text('UPDATE attendance_branches SET is_active=FALSE WHERE id=102'));database.commit()
    with pytest.raises(HTTPException):save(database,102,driver_out='100')
    with pytest.raises(HTTPException):
        mortuary.save_settings(mortuary.SavePolicy(week=DEFAULT_WEEK,rates={},branch_id=101,employee_user_id=11),OWNER,database)
    assert database.execute(text('SELECT COUNT(*) FROM commission_branch_rates')).scalar()==0
