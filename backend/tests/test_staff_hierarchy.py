import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.franchise_staff import (
    UpdateEmployeeRequest,
    _active_manager_profile,
    _ensure_active_office_assignment,
    _ensure_manager_assignment,
    _ensure_staff_integrity,
    _require_superuser,
    _create_user,
    _ensure_email_available,
    _ensure_staff_identity_unique,
    _preserve_blank_identity_values,
    _staff_integrity_report,
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


def test_blank_identity_fields_are_preserved_on_edit():
    values = _preserve_blank_identity_values({
        "id_number": "",
        "username": "   ",
        "password": "",
        "employee_number": "",
        "email": "",
        "contact_number": "",
        "name": "Updated",
    })

    assert values == {"contact_number": "", "name": "Updated"}


class EmptyResult:
    def first(self):
        return None

    def mappings(self):
        return self


class RecordingSession:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return EmptyResult()


def test_create_checks_do_not_bind_untyped_null_parameters():
    session = RecordingSession()

    assert _unique_username(session, "manager_one") == "manager_one"
    assert _ensure_email_available(session, "manager@example.com") == "manager@example.com"
    _ensure_staff_identity_unique(
        session,
        franchise_user_id=2,
        employee_number="MAG001",
        id_number="940806 0236 086",
    )

    assert all("IS NULL" not in sql for sql, _ in session.calls)
    assert all("exclude_user_id" not in params for _, params in session.calls)


def test_edit_checks_include_typed_exclusion_predicates():
    session = RecordingSession()

    _unique_username(session, "manager_one", exclude_user_id=42)
    _ensure_email_available(session, "manager@example.com", exclude_user_id=42)
    _ensure_staff_identity_unique(
        session,
        franchise_user_id=2,
        employee_number="MAG001",
        exclude_user_id=42,
    )

    assert all(params.get("exclude_user_id") == 42 for _, params in session.calls)
    assert all("<> :exclude_user_id" in sql for sql, _ in session.calls)


class ManagerProfileResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class ManagerProfileSession:
    def execute(self, statement, params):
        assert "FROM manager_users" in str(statement)
        assert params == {"user_id": 71}
        return ManagerProfileResult({"id": 9, "franchise_user_id": 3})


def test_active_manager_profile_is_authoritative_for_staff_read_scope():
    assert _active_manager_profile(ManagerProfileSession(), 71) == {
        "id": 9,
        "franchise_user_id": 3,
    }


def test_staff_mutations_require_superuser(monkeypatch):
    from app.api import franchise_staff

    monkeypatch.setattr(franchise_staff, "_is_superuser", lambda db, user: False)
    with pytest.raises(HTTPException, match="Only SuperUser can manage staff"):
        _require_superuser(object(), object())


def test_superuser_passes_staff_mutation_guard(monkeypatch):
    from app.api import franchise_staff

    monkeypatch.setattr(franchise_staff, "_is_superuser", lambda db, user: True)
    assert _require_superuser(object(), object()) is None


class SequenceResult:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class IntegritySession:
    def __init__(self, missing_fragment=None):
        self.missing_fragment = missing_fragment
        self.calls = []

    def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params))
        if self.missing_fragment and self.missing_fragment in sql:
            return SequenceResult(None)
        return SequenceResult({"id": params.get("user_id") or params.get("franchise_user_id") or params.get("manager_user_id") or params.get("area_id") or 1})


def test_staff_integrity_checks_user_role_franchise_office_and_manager():
    session = IntegritySession()

    _ensure_staff_integrity(
        session,
        staff_type="employee",
        user_id=8,
        franchise_user_id=3,
        office_area_id=4,
        manager_user_id=7,
    )

    sql = "\n".join(statement for statement, _ in session.calls)
    assert "FROM users" in sql
    assert "JOIN roles" in sql
    assert "FROM franchise_users" in sql
    assert "FROM areas" in sql
    assert "FROM manager_users" in sql


def test_staff_integrity_rejects_orphaned_manager_assignment():
    session = IntegritySession(missing_fragment="FROM manager_users")

    with pytest.raises(HTTPException, match="Selected manager is not under this franchise"):
        _ensure_manager_assignment(session, manager_user_id=99, franchise_user_id=3)


def test_staff_integrity_rejects_missing_active_office_assignment():
    session = IntegritySession(missing_fragment="FROM gps_allocations_per_user")

    with pytest.raises(HTTPException, match="active office assignment"):
        _ensure_active_office_assignment(session, user_id=10, franchise_user_id=3, office_area_id=5)


class RowsResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class ReportSession:
    def execute(self, statement):
        assert "UNION ALL" in str(statement)
        return RowsResult([
            {
                "staff_type": "manager",
                "staff_id": 1,
                "user_id": 11,
                "franchise_user_id": 3,
                "manager_user_id": None,
                "office_area_id": 4,
                "user_exists": True,
                "franchise_exists": True,
                "role_exists": True,
                "office_exists": True,
                "manager_exists": True,
            },
            {
                "staff_type": "employee",
                "staff_id": 2,
                "user_id": 12,
                "franchise_user_id": 3,
                "manager_user_id": 99,
                "office_area_id": None,
                "user_exists": True,
                "franchise_exists": True,
                "role_exists": False,
                "office_exists": False,
                "manager_exists": False,
            },
        ])


def test_staff_integrity_report_lists_existing_orphaned_records():
    report = _staff_integrity_report(ReportSession())

    assert report["total_staff"] == 2
    assert report["invalid_count"] == 3
    assert {issue["issue"] for issue in report["issues"]} == {
        "Missing required user role",
        "Missing active office assignment",
        "Missing or cross-franchise manager assignment",
    }
