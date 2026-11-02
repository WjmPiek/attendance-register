from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.services.business_handoff import fill_business_profile


def handoff():
    return dict(primary_franchise_id=1, active_franchise_id=2,
                branch_scope=[{'id':1,'name':'Northcliff'},{'id':2,'name':'Benoni'}],
                business_profile=dict(franchise_id=1,franchise_name='Northcliff',business_name='Example Pty Ltd',
                                      vat_number='4000000000',office_address='Example address',contact_number='0100000000'))


def test_missing_holder_details_use_primary_franchise_even_when_linked_branch_is_open():
    profile=SimpleNamespace(business_name='Northcliff')
    fill_business_profile(profile,handoff())
    assert profile.business_name=='Example Pty Ltd'
    assert profile.office_address=='Example address'
    assert profile.vat_number=='4000000000'
    assert profile.franchise_name=='Northcliff'


def test_existing_local_values_are_preserved_and_empty_source_never_erases_data():
    profile=SimpleNamespace(business_name='Locally saved company',office_address='Local address',vat_number='Local VAT')
    fill_business_profile(profile,handoff())
    assert profile.business_name=='Locally saved company' and profile.office_address=='Local address'
    assert profile.vat_number=='Local VAT'
    payload=handoff();payload['business_profile']['office_address']=''
    fill_business_profile(profile,payload)
    assert profile.office_address=='Local address'


def test_unapproved_primary_business_details_are_rejected():
    payload=handoff();payload['business_profile']['franchise_id']=2
    with pytest.raises(HTTPException): fill_business_profile(SimpleNamespace(),payload)
    payload=handoff();payload['branch_scope']=[{'id':2,'name':'Benoni'}]
    with pytest.raises(HTTPException): fill_business_profile(SimpleNamespace(),payload)


def test_old_handoffs_and_oversized_fields_do_not_break_launch():
    profile=SimpleNamespace()
    fill_business_profile(profile,{})
    payload=handoff();payload['business_profile']['contact_number']='1'*51
    fill_business_profile(profile,payload)
    assert not hasattr(profile,'contact_number')
