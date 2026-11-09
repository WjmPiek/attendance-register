import asyncio
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import text

from app.api import receipt_commissions as api, commission
from app.services.receipt_commissions import branch_options, save_branch_options, enabled_for_branch, require_manual_eligibility
from tests.test_mortuary_book import database, record, import_payload, quote_and_import
from tests.test_receipt_commissions import configure, receipt, stage_receipt, calculate, OWNER


def isolated_options(db, first, second):
    save_branch_options(db,2,11,{101:{'enabled_types':first},102:{'enabled_types':second}},1)
    save_branch_options(db,2,12,{},1)
    db.commit()


def paired_at(db, name, recipients=(11,)):
    quote_and_import(db,import_payload([dict(record(),branch=name)]))
    result=stage_receipt(db,[dict(receipt(),branch=name,gross_received='1150.00')],people=recipients)
    payload,q=calculate(db,result['document_ids'])
    api.settle(payload,OWNER,db)
    return q


def test_permissions_are_independent_for_each_linked_branch(database):
    configure(database)
    isolated_options(database,['removals'],['invoice_commission'])
    assert enabled_for_branch(database,2,11,'removals',101)
    assert not enabled_for_branch(database,2,11,'removals',102)
    assert enabled_for_branch(database,2,11,'invoice_commission',102)
    assert not enabled_for_branch(database,2,11,'invoice_commission',101)
    q=paired_at(database,'EXAMPLE',recipients=())
    assert sum(r['state']=='ready' for r in q['items'])==1
    q=paired_at(database,'EXAMPLE SOUTH')
    assert next(r for r in q['items'] if r.get('category')=='invoice_commission')['amount']=='20.00'
    assert all(r['state']=='blocked' for r in q['items'] if r.get('category')=='removals')
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar()==2


def test_receipt_cannot_select_an_employee_enabled_only_at_another_branch(database):
    configure(database);isolated_options(database,['removals'],['invoice_commission'])
    with pytest.raises(HTTPException,match='enabled'):
        stage_receipt(database,[receipt()],people=(11,))
    assert database.execute(text('SELECT COUNT(*) FROM commission_documents')).scalar()==0


def test_branch_statements_and_pdfs_use_earning_branch_not_home_branch(database):
    configure(database);isolated_options(database,['removals'],['invoice_commission'])
    paired_at(database,'EXAMPLE',recipients=());paired_at(database,'EXAMPLE SOUTH')
    first=commission.entries(employee_user_id=11,earning_branch_id=101,current_user=OWNER,db=database)
    second=commission.entries(employee_user_id=11,earning_branch_id=102,current_user=OWNER,db=database)
    assert first['total']==Decimal('200') and {r['commission_type'] for r in first['items']}=={'removals'}
    assert second['total']==Decimal('20') and {r['commission_type'] for r in second['items']}=={'invoice_commission'}
    async def content(response):return b''.join([part async for part in response.body_iterator])
    pdf=asyncio.run(content(api.report('2026-10',branch_id=102,employee_user_id=11,current_user=OWNER,db=database)))
    printed='\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
    assert 'EXAMPLE SOUTH' in printed and 'MF File Receipts subtotal: R 20.00' in printed
    assert 'Removals subtotal' not in printed
    # Moving the home branch does not move past earnings between branch statements.
    database.execute(text('UPDATE employee_branch_assignments SET branch_id=102 WHERE employee_user_id=11'));database.commit()
    assert commission.entries(employee_user_id=11,earning_branch_id=101,current_user=OWNER,db=database)['total']==Decimal('200')


def test_each_branch_can_have_its_own_employee_receipt_percentage(database):
    configure(database)
    save_branch_options(database,2,11,{101:{'enabled_types':['invoice_commission'],'receipt_percentage':'3'},102:{'enabled_types':['invoice_commission'],'receipt_percentage':'5'}},1)
    save_branch_options(database,2,12,{},1);database.commit()
    paired_at(database,'EXAMPLE');paired_at(database,'EXAMPLE SOUTH')
    assert commission.entries(employee_user_id=11,earning_branch_id=101,current_user=OWNER,db=database)['total']==Decimal('30')
    assert commission.entries(employee_user_id=11,earning_branch_id=102,current_user=OWNER,db=database)['total']==Decimal('50')


def test_editing_one_branch_preserves_other_branch_permissions(database):
    configure(database)
    values=branch_options(database,2,11)
    values['101']['enabled_types']=[]
    api.save_options(api.OptionIn(employee_user_id=11,commission_branches=values),OWNER,database)
    updated=branch_options(database,2,11)
    assert updated['101']['enabled_types']==[]
    assert set(updated['102']['enabled_types'])=={'removals','invoice_commission'}
    with pytest.raises(HTTPException):
        api.save_options(api.OptionIn(employee_user_id=11,commission_branches={900:{'enabled_types':['removals']}}),OWNER,database)


def test_managers_have_the_same_branch_specific_commission_controls(database):
    configure(database)
    database.execute(text("INSERT INTO users VALUES(13,'Morgan Example',NULL,TRUE)"))
    database.execute(text("INSERT INTO manager_users(id,user_id,franchise_user_id,name,surname,employee_number,is_active) VALUES(13,13,2,'Morgan','Example','13',TRUE)"))
    database.execute(text('INSERT INTO employee_branch_assignments VALUES(2,13,101,FALSE)'))
    save_branch_options(database,2,13,{102:{'enabled_types':['invoice_commission'],'receipt_percentage':'4'}},1);database.commit()
    q=paired_at(database,'EXAMPLE SOUTH',recipients=(13,))
    row=next(r for r in q['items'] if r.get('employee_user_id')==13)
    assert row['amount']=='40.00' and row['earning_branch_id']==102


def test_manual_categories_require_the_selected_branch_and_store_it(database):
    configure(database);isolated_options(database,[],['joinings'])
    person={'franchise_user_id':2,'user_id':11}
    with pytest.raises(HTTPException,match='selected branch'):
        require_manual_eligibility(database,person,'joinings',101)
    assert require_manual_eligibility(database,person,'joinings',102)==102
    database.execute(text('CREATE TABLE commission_structures(id INTEGER PRIMARY KEY,franchise_user_id INT,commission_type TEXT,label TEXT,rate NUMERIC,overtime_multiplier NUMERIC,is_active BOOLEAN)'))
    database.execute(text("INSERT INTO commission_structures VALUES(1,2,'joinings','Joinings',25,NULL,TRUE)"));database.commit()
    quote_and_import(database,import_payload([dict(record(),branch='EXAMPLE SOUTH',reference='JOIN-BRANCH')]))
    stage_receipt(database,[dict(receipt(),branch='EXAMPLE SOUTH',reference='JOIN-BRANCH')],people=())
    saved=commission.create_entry(commission.EntryIn(employee_user_id=11,commission_type='joinings',service_date='2026-11-02',reference='JOIN-BRANCH',earning_branch_id=102,claim_deceased='Example Person'),OWNER,database)
    assert saved['earning_branch_id']==102 and saved['branch_name']=='EXAMPLE SOUTH'


def test_old_quote_cannot_pay_after_branch_permission_is_removed(database):
    configure(database)
    quote_and_import(database,import_payload())
    result=stage_receipt(database)
    payload,_=calculate(database,result['document_ids'])
    save_branch_options(database,2,11,{102:{'enabled_types':['invoice_commission']}},1);database.commit()
    with pytest.raises(HTTPException,match='changed'):
        api.settle(payload,OWNER,database)
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar()==0


def test_staff_view_filters_home_branch_independently_of_commission_branch(database):
    from app.api.franchise_staff import _staff_branch_rows
    configure(database)
    # Aubrey works at branch 102 even when enabled to earn for branch 101.
    rows=[{'user_id':11,'name':'Ewald'},{'user_id':12,'name':'Aubrey'}]
    assert [r['user_id'] for r in _staff_branch_rows(database,rows,101)]==[11]
    assert [r['user_id'] for r in _staff_branch_rows(database,rows,102)]==[12]
    assert len(_staff_branch_rows(database,rows))==2
    assert _staff_branch_rows(database,rows,900)==[]


def test_main_system_profile_handoff_opens_the_same_linked_branch(database):
    from app.services.attendance_branches import launch_branch_context
    assert launch_branch_context(database,2,{'active_franchise_id':1})==101
    assert launch_branch_context(database,2,{'active_franchise_id':2})==102
    assert launch_branch_context(database,2,{}) is None
    with pytest.raises(HTTPException):launch_branch_context(database,2,{'active_franchise_id':9})


@pytest.mark.parametrize('manager', [False, True])
def test_selected_branch_save_keeps_main_and_other_overrides_and_blocks_excluded_earnings(database, manager):
    configure(database)
    if manager:
        database.execute(text('DELETE FROM employee_users WHERE user_id=11'))
        database.execute(text("INSERT INTO manager_users(id,user_id,franchise_user_id,name,surname,employee_number,is_active) VALUES(11,11,2,'Ewald','Example','11',TRUE)"))
    database.execute(text("INSERT INTO attendance_branches VALUES(103,2,3,'EXAMPLE EAST',NULL,TRUE,TRUE)"))
    save_branch_options(database,2,11,{101:{'enabled_types':['removals','invoice_commission'],'rates':{'driver_out':'250','driver_invoice_commission':'4'}}},1)
    save_branch_options(database,2,12,{},1)
    database.commit()
    # Turn off removals at South without submitting the settings for any other branch.
    api.save_options(api.OptionIn(employee_user_id=11,branch_id=102,
        commission_branches={102:{'enabled_types':['invoice_commission'],'rates':{'driver_invoice_commission':'6'}}}),OWNER,database)
    choices=branch_options(database,2,11)
    assert choices['101']['rates']['driver_out']=='250'
    assert choices['103']['inherit_home'] and enabled_for_branch(database,2,11,'removals',103)
    assert not choices['102']['inherit_home'] and not enabled_for_branch(database,2,11,'removals',102)
    assert choices['102']['rates']['driver_invoice_commission']=='6'
    with pytest.raises(HTTPException,match='selected branch'):
        require_manual_eligibility(database,{'user_id':11,'franchise_user_id':2},'removals',102)
    q=paired_at(database,'EXAMPLE SOUTH')
    assert next(r for r in q['items'] if r.get('category')=='invoice_commission')['amount']=='60.00'
    assert not any(r['state']=='ready' and r.get('category')=='removals' for r in q['items'])
    assert commission.entries(employee_user_id=11,earning_branch_id=102,current_user=OWNER,db=database)['total']==Decimal('60')
    # Later main-branch changes flow to inherited East, while South stays independent.
    api.save_options(api.OptionIn(employee_user_id=11,branch_id=101,
        commission_branches={101:{'enabled_types':['removals'],'rates':{'driver_out':'275'}}}),OWNER,database)
    choices=branch_options(database,2,11)
    assert choices['103']['enabled_types']==['removals'] and choices['103']['rates']['driver_out']=='275'
    assert choices['102']['enabled_types']==['invoice_commission'] and choices['102']['rates']['driver_invoice_commission']=='6'
    assert enabled_for_branch(database,2,11,'invoice_commission',102)


def test_branch_save_can_disable_everything_and_restore_live_inheritance(database):
    configure(database)
    database.execute(text("UPDATE employee_commission_options SET rate=7 WHERE employee_user_id=11 AND commission_type='invoice_commission'"))
    database.commit()
    api.save_options(api.OptionIn(employee_user_id=11,branch_id=102,receipt_percentage=99,
        commission_branches={102:{'enabled_types':[]}}),OWNER,database)
    assert branch_options(database,2,11)['102']['enabled_types']==[]
    assert enabled_for_branch(database,2,11,'removals',101)
    assert database.execute(text("SELECT rate FROM employee_commission_options WHERE employee_user_id=11 AND commission_type='invoice_commission'")).scalar()==7
    api.save_options(api.OptionIn(employee_user_id=11,branch_id=102,
        commission_branches={102:{'inherit_home':True}}),OWNER,database)
    assert enabled_for_branch(database,2,11,'removals',102)
    assert branch_options(database,2,11)['102']['inherit_home']


@pytest.mark.parametrize('values', [{}, {101:{'enabled_types':[]}}, {101:{'enabled_types':[]},102:{'enabled_types':[]}}, None])
def test_scoped_save_rejects_missing_or_other_branch_settings_without_changing_grants(database, values):
    configure(database)
    before=branch_options(database,2,11)
    with pytest.raises(HTTPException):
        api.save_options(api.OptionIn(employee_user_id=11,branch_id=102,commission_branches=values),OWNER,database)
    assert branch_options(database,2,11)==before
