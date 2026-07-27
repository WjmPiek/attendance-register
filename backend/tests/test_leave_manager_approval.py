from types import SimpleNamespace

from app.api import leave


def test_manager_can_decide_only_linked_employee_leave(monkeypatch):
    manager_user = SimpleNamespace(id=50)
    monkeypatch.setattr(leave, "_roles", lambda db, user: {"ManagerUser"})
    monkeypatch.setattr(
        leave,
        "_manager_profile",
        lambda db, user_id: {"manager_user_id": 7, "franchise_user_id": 3},
    )

    assert leave._can_decide(
        object(),
        manager_user,
        {"applicant_user_id": 61, "manager_user_id": 7, "franchise_user_id": 3},
    )
    assert not leave._can_decide(
        object(),
        manager_user,
        {"applicant_user_id": 62, "manager_user_id": 8, "franchise_user_id": 3},
    )
    assert not leave._can_decide(
        object(),
        manager_user,
        {"applicant_user_id": 50, "manager_user_id": 7, "franchise_user_id": 3},
    )
