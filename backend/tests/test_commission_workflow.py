from decimal import Decimal
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
