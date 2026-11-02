import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api import commission, receipt_commissions as api
from app.services.attendance_branches import import_scope, branches, assign_staff
from app.services.receipt_commissions import payment_eligibility, save_branch_options
from tests.test_mortuary_book import database, record, import_payload, quote_and_import
from tests.test_receipt_commissions import OWNER, receipt, stage_receipt, calculate
from tests.test_commission_payment_proof import manual_setup, payload

STAFF = SimpleNamespace(id=11)


def evidence(db):
    quote_and_import(db, import_payload())
    stage_receipt(db, people=())


def rates(db, **values):
    policy = json.loads(db.execute(text('SELECT policy FROM mortuary_policies WHERE employee_user_id=0')).scalar_one())
    policy['rates'].update(values)
    db.execute(text('UPDATE mortuary_policies SET policy=:p WHERE employee_user_id=0'), {'p': json.dumps(policy)})
    db.commit()


def test_red_claim_becomes_green_after_upload_then_holder_approves(database):
    manual_setup(database)
    api.set_uploaders(api.UploadersIn(employee_user_ids=[11, 12]), OWNER, database)
    saved = commission.create_entry(payload(), STAFF, database)
    assert saved['status'] == 'pending' and not saved['documents_valid']
    notices = database.execute(text("SELECT recipient_user_id FROM notifications WHERE subject='Document uploads required'")).scalars().all()
    assert set(notices) == {11, 12}
    assert not commission.entries(current_user=STAFF, db=database)['items'][0]['payment_eligible']
    evidence(database)
    row = commission.entries(current_user=STAFF, db=database)['items'][0]
    assert row['payment_eligible'] and Decimal(row['expected_amount']) == 100
    assert commission.entries(current_user=STAFF, db=database)['total'] == 0
    approved = commission.review(saved['id'], commission.ReviewIn(**payload().model_dump(), status='approved'), OWNER, database)
    assert approved['status'] == 'approved'
    assert commission.entries(current_user=STAFF, db=database)['total'] == 100


@pytest.mark.parametrize('change', [{'quantity': 2}, {'rate_override': 999}, {'claim_deceased': ''}, {'commission_type': 'removals'}])
def test_claim_cannot_set_own_price_or_skip_required_details(database, change):
    manual_setup(database)
    with pytest.raises(HTTPException):
        commission.claim_quote(payload().model_copy(update=change), STAFF, database)
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar() == 0


def test_claimant_identity_is_login_and_other_staff_remain_private(database):
    manual_setup(database)
    submitted = commission.create_entry(payload().model_copy(update={'employee_user_id': 12}), STAFF, database)
    assert submitted['employee_user_id'] == 11
    with pytest.raises(HTTPException):
        commission.entries(employee_user_id=12, current_user=STAFF, db=database)
    with pytest.raises(HTTPException, match='holder'):
        commission.review(submitted['id'], commission.ReviewIn(**payload().model_dump(), status='approved'), STAFF, database)


def test_name_mismatch_blocks_even_when_three_documents_match(database):
    manual_setup(database); evidence(database)
    quote = commission.claim_quote(payload().model_copy(update={'claim_deceased': 'Other Person'}), STAFF, database)
    assert not quote['documents_valid'] and 'name and surname' in quote['notice']


def test_fixed_role_rate_and_overtime_do_not_multiply_hours(database):
    manual_setup(database); evidence(database)
    rates(database, assistant_grave_service='75', driver_overtime='125')
    save_branch_options(database, 2, 11, {101: {'enabled_types': ['grave_service', 'overtime']}}, 1); database.commit()
    assistant = commission.claim_quote(payload().model_copy(update={'commission_role': 'assistant'}), STAFF, database)
    overtime = commission.claim_quote(payload().model_copy(update={'commission_type': 'overtime', 'hours': Decimal(12), 'hourly_rate': Decimal(500)}), STAFF, database)
    assert assistant['amount'] == '75.00' and overtime['amount'] == '125.00'


def test_duplicate_case_cannot_be_multiplied_by_date_or_mf_format(database):
    manual_setup(database)
    commission.create_entry(payload(), STAFF, database)
    with pytest.raises(HTTPException, match='already has'):
        commission.create_entry(payload().model_copy(update={'reference': 'MF TEST-1315', 'service_date': '2026-11-03'}), STAFF, database)


def test_bulk_approval_rolls_back_all_if_one_case_lacks_proof(database):
    manual_setup(database)
    good = commission.create_entry(payload(), STAFF, database)
    bad = commission.create_entry(payload().model_copy(update={'reference': 'MISSING'}), STAFF, database)
    evidence(database)
    with pytest.raises(HTTPException):
        commission.bulk_review(commission.BulkReviewIn(entry_ids=[good['id'], bad['id']], status='approved'), OWNER, database)
    assert set(database.execute(text('SELECT status FROM commission_entries')).scalars()) == {'pending'}


def test_multiple_uploaders_can_be_granted_and_revoked_without_approval_access(database):
    manual_setup(database)
    api.set_uploaders(api.UploadersIn(employee_user_ids=[11, 12]), OWNER, database)
    assert import_scope(database, STAFF) == 2 and import_scope(database, SimpleNamespace(id=12)) == 2
    with pytest.raises(HTTPException, match='holder'):
        api.set_uploaders(api.UploadersIn(employee_user_ids=[11]), STAFF, database)
    with pytest.raises(HTTPException, match='holder'):
        api.settle(api.CalculateIn(document_ids=[1]), STAFF, database)
    with pytest.raises(HTTPException, match='active staff'):
        api.set_uploaders(api.UploadersIn(employee_user_ids=[99]), OWNER, database)
    api.set_uploaders(api.UploadersIn(employee_user_ids=[12]), OWNER, database)
    with pytest.raises(HTTPException, match='not enabled'):
        import_scope(database, STAFF)
    assert import_scope(database, SimpleNamespace(id=12)) == 2


def outside_evidence(db, bid):
    book = dict(record(), branch='OUTSIDE', external_branch_id=bid)
    quote_and_import(db, import_payload([book]))
    inv = dict(receipt(), branch='OUTSIDE', external_branch_id=bid, invoice_total='23580.61', vat_registered=True,
               vat_number='4000000000', vat_rate='15', commission_base='20504.88', vat_amount='3075.73', vat_issue=None)
    api.save_document(db, 2, 'invoice', inv, [], 1)
    return stage_receipt(db, [dict(receipt(), branch='OUTSIDE', external_branch_id=bid)], people=(), with_invoice=False)


def test_outside_branch_has_separate_scope_and_extra_fee_once_per_staff_case(database):
    manual_setup(database)
    outside = api.declare_external_branch(api.ExternalBranchIn(name='OUTSIDE', vat_number='4000000000'), OWNER, database)
    bid = outside['id']
    assert bid not in {b['id'] for b in branches(database, 2)}
    with pytest.raises(HTTPException):
        assign_staff(database, 2, 11, bid)
    with pytest.raises(HTTPException):
        api.require_branch(database, 2, 'EXAMPLE', bid)
    rates(database, driver_other_branch='50', driver_church_service='60')
    save_branch_options(database, 2, 11, {101: {'enabled_types': ['grave_service', 'church_service', 'service_other_branch', 'removals']}}, 1); database.commit()
    outside_evidence(database, bid)
    request = payload().model_copy(update={'earning_branch_id': bid})
    quote = commission.claim_quote(request, STAFF, database)
    assert quote['documents_valid'] and quote['additional_fee']['amount'] == '50.00'
    commission.create_entry(request, OWNER, database)
    commission.create_entry(request.model_copy(update={'commission_type': 'church_service'}), OWNER, database)
    assert database.execute(text("SELECT COUNT(*) FROM commission_entries WHERE commission_type='service_other_branch'")).scalar() == 1
    ids = database.execute(text('SELECT id FROM commission_documents')).scalars().all()
    request, plan = calculate(database, ids)
    assert not any(row['category'] == 'service_other_branch' and row['state'] == 'ready' and row['employee_user_id'] == 11 for row in plan['items'])
    api.settle(request, OWNER, database)
    assert database.execute(text("SELECT COUNT(*) FROM commission_entries WHERE commission_type='service_other_branch'")).scalar() == 1


def test_linked_branches_never_get_external_additional_fee(database):
    manual_setup(database); evidence(database)
    rates(database, driver_other_branch='50')
    save_branch_options(database, 2, 11, {101: {'enabled_types': ['grave_service', 'service_other_branch']}}, 1); database.commit()
    assert commission.claim_quote(payload(), STAFF, database)['additional_fee'] is None
    with pytest.raises(HTTPException, match='linked branch'):
        api.declare_external_branch(api.ExternalBranchIn(name='EXAMPLE'), OWNER, database)
    with pytest.raises(HTTPException, match='holder'):
        api.declare_external_branch(api.ExternalBranchIn(name='OUTSIDE'), STAFF, database)


def test_delegate_receipt_upload_does_not_allow_settlement(database):
    manual_setup(database)
    api.set_uploaders(api.UploadersIn(employee_user_ids=[11]), OWNER, database)
    r = receipt()
    token = api.signer().dumps({'kind': 'receipts', 'user_id': 11, 'franchise_user_id': 2, 'records': [r]})
    result = api.stage(api.StageIn(preview_token=token, confirmed_franchise=True, allocations=[{'record': 0, 'employee_user_ids': []}]), STAFF, database)
    assert result['saved'] == 1
    assert api.get_settings(current_user=STAFF, db=database)['can_approve'] is False
    with pytest.raises(HTTPException, match='holder'):
        api.settle(api.CalculateIn(document_ids=result['document_ids']), STAFF, database)
