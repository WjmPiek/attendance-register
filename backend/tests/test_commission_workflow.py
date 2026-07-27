from decimal import Decimal
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import commission


def payload(**changes):
    values = {
        "employee_user_id": 20,
        "commission_type": "joinings",
        "service_date": "2026-07-24",
        "reference": "JOIN-001",
        "quantity": Decimal("2"),
    }
    values.update(changes)
    return commission.EntryIn(**values)


def test_joinings_are_supported_and_calculated_by_quantity():
    assert "joinings" in commission.COMMISSION_TYPES
    rate, amount = commission._calculate(
        {"rate": Decimal("75"), "overtime_multiplier": None},
        payload(),
    )
    assert rate == Decimal("75")
    assert amount == Decimal("150.00")


def test_fixed_commission_rejects_fractional_quantity():
    with pytest.raises(HTTPException, match="whole number"):
        commission._calculate(
            {"rate": Decimal("75"), "overtime_multiplier": None},
            payload(quantity=Decimal("1.5")),
        )


def test_manager_cannot_review_own_submission(monkeypatch):
    monkeypatch.setattr(
        commission,
        "_profile",
        lambda db, user: ({"ManagerUser"}, 2, 5, user.id, "manager"),
    )
    entry = {
        "status": "pending",
        "is_cancelled": False,
        "created_by_user_id": 10,
        "employee_user_id": 10,
    }
    participant = {"staff_type": "manager", "manager_user_id": None}
    with pytest.raises(HTTPException, match="own submission"):
        commission._assert_review_allowed(None, SimpleNamespace(id=10), entry, participant)


def test_manager_can_review_assigned_employee(monkeypatch):
    monkeypatch.setattr(
        commission,
        "_profile",
        lambda db, user: ({"ManagerUser"}, 2, 5, user.id, "manager"),
    )
    entry = {
        "status": "pending",
        "is_cancelled": False,
        "created_by_user_id": 20,
        "employee_user_id": 20,
    }
    participant = {"staff_type": "employee", "manager_user_id": 5}
    commission._assert_review_allowed(None, SimpleNamespace(id=10), entry, participant)


def test_reviewed_submission_cannot_be_reviewed_again(monkeypatch):
    monkeypatch.setattr(
        commission,
        "_profile",
        lambda db, user: ({"FranchiseUser"}, 2, None, None, "franchise"),
    )
    entry = {
        "status": "approved",
        "is_cancelled": False,
        "created_by_user_id": 20,
        "employee_user_id": 20,
    }
    with pytest.raises(HTTPException, match="pending"):
        commission._assert_review_allowed(
            None,
            SimpleNamespace(id=10),
            entry,
            {"staff_type": "employee", "manager_user_id": 5},
        )


class _NoDuplicateResult:
    def scalar(self):
        return None


class _CaptureDb:
    def __init__(self):
        self.statement = ""
        self.params = {}

    def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return _NoDuplicateResult()


def test_new_submission_duplicate_check_omits_nullable_exclusion_parameter():
    db = _CaptureDb()
    commission._assert_not_duplicate(db, 2, 20, payload(), exclude_entry_id=None)
    assert "exclude_id" not in db.params
    assert "id<>:exclude_id" not in db.statement


def test_review_duplicate_check_excludes_current_entry():
    db = _CaptureDb()
    commission._assert_not_duplicate(db, 2, 20, payload(), exclude_entry_id=55)
    assert db.params["exclude_id"] == 55
    assert "id<>:exclude_id" in db.statement


def test_submission_insert_does_not_reuse_status_in_sql_case_expression():
    source = inspect.getsource(commission.create_entry)
    assert "CASE WHEN :status" not in source
    assert ":reviewed_at,:reviewed_by" in source


class _RowsResult:
    def mappings(self):
        return self

    def all(self):
        return []


class _RowsDb:
    def __init__(self):
        self.statement = ""
        self.params = {}

    def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return _RowsResult()


def test_manager_landing_history_contains_only_manager_commissions(monkeypatch):
    monkeypatch.setattr(
        commission,
        "_profile",
        lambda db, user: ({"ManagerUser"}, 2, 5, user.id, "manager"),
    )
    db = _RowsDb()
    commission._rows(db, SimpleNamespace(id=10))
    assert "c.employee_user_id=:uid" in db.statement
    assert "ep.manager_user_id=:mid" not in db.statement
    assert db.params == {"uid": 10}


def test_manager_can_load_one_linked_employee_separately(monkeypatch):
    monkeypatch.setattr(
        commission,
        "_profile",
        lambda db, user: ({"ManagerUser"}, 2, 5, user.id, "manager"),
    )
    monkeypatch.setattr(
        commission,
        "_participant",
        lambda db, user, user_id: {"user_id": user_id, "franchise_user_id": 2},
    )
    db = _RowsDb()
    commission._rows(db, SimpleNamespace(id=10), employee_user_id=20)
    assert "c.employee_user_id=:employee" in db.statement
    assert db.params == {"employee": 20}
