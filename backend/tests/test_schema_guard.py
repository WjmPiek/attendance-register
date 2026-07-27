import pytest

from app.services import schema_guard


class FakeInspector:
    def __init__(self, email_nullable: bool, attendance_evidence: bool = True):
        self.email_nullable = email_nullable
        self.attendance_evidence = attendance_evidence

    def get_table_names(self):
        return list(schema_guard.REQUIRED_TABLES)

    def get_columns(self, table_name):
        if table_name == "users":
            return [
                {"name": "id", "nullable": False},
                {"name": "email", "nullable": self.email_nullable},
            ]
        if table_name == "attendance_events":
            names = {"id", "attendance_photo", "attendance_photo_mime", "attendance_photo_filename", "photo_status"} if self.attendance_evidence else {"id"}
            return [{"name": name, "nullable": name != "id"} for name in names]
        raise AssertionError(table_name)


def test_schema_guard_rejects_legacy_required_email(monkeypatch):
    monkeypatch.setattr(schema_guard, "inspect", lambda _: FakeInspector(False))

    with pytest.raises(RuntimeError, match="users.email must allow NULL"):
        schema_guard.assert_operational_schema(object())


def test_schema_guard_accepts_optional_email(monkeypatch):
    monkeypatch.setattr(schema_guard, "inspect", lambda _: FakeInspector(True))

    schema_guard.assert_operational_schema(object())


def test_schema_guard_rejects_missing_attendance_evidence_columns(monkeypatch):
    monkeypatch.setattr(schema_guard, "inspect", lambda _: FakeInspector(True, False))

    with pytest.raises(RuntimeError, match="Missing attendance evidence columns"):
        schema_guard.assert_operational_schema(object())
