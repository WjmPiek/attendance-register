from datetime import datetime
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text

from app.api import attendance, mortuary, franchise_staff, receipt_commissions as receipts
from app.services.mortuary import price_removal
from app.services.staff_hours import work_window
from tests.test_mortuary_book import database, policy, record, import_payload, quote_and_import
from tests.test_receipt_commissions import configure, stage_receipt, calculate, OWNER


def week():
    return [{'start': '09:00', 'end': '16:00'} for _ in range(5)] + [{'start': '08:00', 'end': '12:00'}, None]


def test_weekly_hours_apply_by_day_instead_of_commission_policy_hours():
    staff = {'work_week': json.dumps(week()), 'work_start_time': '08:00', 'work_end_time': '17:00'}
    morning = dict(record(), date_in='2026-11-02', time_in='08:30')
    assert price_removal(morning, 'driver', policy(), staff_hours=staff)['amount'] == '200.00'
    assert price_removal(dict(morning, time_in='09:00'), 'driver', policy(), staff_hours=staff)['amount'] == '100.00'
    assert price_removal(dict(morning, date_in='2026-11-07', time_in='12:00'), 'driver', policy(), staff_hours=staff)['amount'] == '200.00'
    closed = week(); closed[0] = None
    assert price_removal(dict(morning, time_in='10:00'), 'driver', policy(), staff_hours={'work_week': closed})['amount'] == '200.00'


@pytest.mark.parametrize('day', ['2026-11-08', '2026-12-25', '2026-08-10'])
def test_sunday_public_holiday_fee_has_priority_and_surcharge_is_additive(day):
    rates = policy()
    rates['rates'].update(driver_sunday_holiday='500', assistant_sunday_holiday='300', driver_other_branch='75', assistant_other_branch='25')
    for role, total in [('driver', '575.00'), ('assistant', '325.00')]:
        result = price_removal(dict(record(), date_in=day, time_in='10:00'), role, rates, other_branch=True, staff_hours={'work_week': week()})
        assert result['amount'] == total and result['fee_category'] == 'sunday_holiday'
    assert price_removal(dict(record(), date_in=day, time_in='10:00'), 'driver', rates, staff_hours={'work_week': week()})['amount'] == '500.00'


def test_additional_fee_does_not_replace_the_business_hours_fee():
    rates = policy(); rates['rates']['driver_other_branch'] = '75'
    result = price_removal(dict(record(), date_in='2026-11-02', time_in='10:00'), 'driver', rates, other_branch=True, staff_hours={'work_week': week()})
    assert result['removal_base_fee'] == '100.00' and result['additional_fee'] == '75.00' and result['amount'] == '175.00'


@pytest.mark.parametrize('schema', [franchise_staff.CreateEmployeeRequest, franchise_staff.CreateManagerRequest, franchise_staff.UpdateEmployeeRequest, franchise_staff.UpdateManagerRequest])
def test_employee_and_manager_requests_preserve_seven_daily_rows(schema):
    values = {'name': 'Example', 'surname': 'Staff', 'employee_role': 'Driver', 'work_week': week()}
    assert len(schema(**values).model_dump()['work_week']) == 7
    assert schema(**values).model_dump()['work_week'][6] is None
    with pytest.raises(ValidationError):
        schema(**{**values, 'work_week': week()[:6]})
    with pytest.raises(ValidationError):
        schema(**{**values, 'work_week': [{'start': '09:00', 'end': '09:00'}] * 7})
    with pytest.raises(ValidationError):
        schema(**{**values, 'work_week': [{'start': '17:00', 'end': '08:00'}] * 7})


def test_attendance_uses_the_same_saved_daily_schedule(database, monkeypatch):
    database.execute(text('UPDATE employee_users SET work_week=:week WHERE user_id=11'), {'week': json.dumps(week())})
    monkeypatch.setattr(attendance, 'now_sa_naive', lambda: datetime(2026, 11, 7, 10))
    assert attendance._get_user_office_hours(database, 11) == ('08:00', '12:00')
    monkeypatch.setattr(attendance, 'now_sa_naive', lambda: datetime(2026, 11, 8, 10))
    assert attendance._get_user_office_hours(database, 11) == (None, None)


def test_new_fees_reach_matched_awards_once_and_reject_stale_schedule_quotes(database):
    configure(database)
    rates = policy(); rates['rates'].update(driver_sunday_holiday='500', assistant_sunday_holiday='300', driver_other_branch='75', assistant_other_branch='25')
    database.execute(text('UPDATE mortuary_policies SET policy=:p'), {'p': json.dumps(rates)})
    quote_and_import(database, import_payload())  # Sunday removal at EXAMPLE; assistant's home is EXAMPLE SOUTH.
    docs = stage_receipt(database)
    payload, quote = calculate(database, docs['document_ids'])
    removal_rows = {r['employee_user_id']: r for r in quote['items'] if r.get('category') == 'removals'}
    assert removal_rows[11]['amount'] == '500.00' and removal_rows[11]['additional_fee'] == '0.00'
    assert removal_rows[12]['amount'] == '300.00' and removal_rows[12]['additional_fee'] == '0.00'
    assert receipts.settle(payload, OWNER, database)['created'] == 4
    again, _ = calculate(database, docs['document_ids'])
    assert receipts.settle(again, OWNER, database)['created'] == 0


def test_editing_staff_hours_invalidates_an_unapproved_book_quote(database):
    r = dict(record(), date_in='2026-11-02', time_in='08:30')
    payload = import_payload([r])
    quoted = mortuary.quote(payload, OWNER, database)
    payload.quote_token = quoted['quote_token']
    database.execute(text('UPDATE employee_users SET work_week=:week WHERE user_id=11'), {'week': json.dumps(week())})
    database.commit()
    with pytest.raises(HTTPException, match='changed'):
        mortuary.import_books(payload, OWNER, database)


def test_existing_staff_without_weekly_hours_keep_saved_times():
    assert work_window({'work_week': None, 'work_start_time': '07:00', 'work_end_time': '15:00'}, 2) == {'start': '07:00', 'end': '15:00'}
