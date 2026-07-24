import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.franchise_staff import (
    UpdateEmployeeRequest,
    _create_user,
    _unique_username,
)
from app.db.base import Base
from app.models.core import Role, User, UserRole


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[User.__table__, Role.__table__, UserRole.__table__],
    )
    with Session(engine) as session:
        session.add_all([
            Role(name="ManagerUser"),
            Role(name="EmployeeUser"),
        ])
        session.commit()
        yield session


def test_staff_account_persists_username_and_exactly_one_role(db):
    user_id = _create_user(
        db,
        full_name="Alex Manager",
        email=None,
        username="alex_manager",
        password="Temp123!",
        role_name="ManagerUser",
    )

    user = db.get(User, user_id)
    assignments = db.query(UserRole).filter(UserRole.user_id == user_id).all()

    assert user.email is None
    assert user.username == "alex_manager"
    assert len(assignments) == 1
    assert assignments[0].role.name == "ManagerUser"


def test_active_login_cannot_be_reused(db):
    _create_user(
        db,
        full_name="First Employee",
        email="employee@example.com",
        username="employee_one",
        password="Temp123!",
        role_name="EmployeeUser",
    )

    with pytest.raises(HTTPException, match="Login already exists"):
        _create_user(
            db,
            full_name="Duplicate Employee",
            email="employee@example.com",
            username="employee_two",
            password="Temp123!",
            role_name="EmployeeUser",
        )


def test_unchanged_username_is_not_renamed_during_edit(db):
    user_id = _create_user(
        db,
        full_name="Existing Manager",
        email=None,
        username="existing_manager",
        password="Temp123!",
        role_name="ManagerUser",
    )

    assert _unique_username(db, "existing_manager", exclude_user_id=user_id) == "existing_manager"


def test_explicit_null_manager_assignment_is_distinguishable_from_omission():
    omitted = UpdateEmployeeRequest()
    cleared = UpdateEmployeeRequest(manager_user_id=None)

    assert "manager_user_id" not in omitted.model_fields_set
    assert "manager_user_id" in cleared.model_fields_set
