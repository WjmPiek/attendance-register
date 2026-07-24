import pytest

from app.services import schema_guard


class FakeInspector:
    def __init__(self, email_nullable: bool):
        self.email_nullable = email_nullable

    def get_table_names(self):
        return list(schema_guard.REQUIRED_TABLES)

    def get_columns(self, table_name):
        assert table_name == "users"
        return [
            {"name": "id", "nullable": False},
            {"name": "email", "nullable": self.email_nullable},
        ]


def test_schema_guard_rejects_legacy_required_email(monkeypatch):
    monkeypatch.setattr(schema_guard, "inspect", lambda _: FakeInspector(False))

    with pytest.raises(RuntimeError, match="users.email must allow NULL"):
        schema_guard.assert_operational_schema(object())


def test_schema_guard_accepts_optional_email(monkeypatch):
    monkeypatch.setattr(schema_guard, "inspect", lambda _: FakeInspector(True))

    schema_guard.assert_operational_schema(object())
