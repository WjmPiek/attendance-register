"""Destructively reset all application data while preserving one protected SuperUser.

Run only against the managed Render PostgreSQL database:
    CONFIRM_DATABASE_RESET=DELETE_ALL_EXCEPT_WJM \
    PYTHONPATH=backend python scripts/reset_render_data_keep_superuser.py
"""
from __future__ import annotations

import os
import sys
from sqlalchemy import inspect, text

from app.core.config import settings
from app.db.session import engine

PROTECTED_EMAIL = "wjm@martinsdirect.com"
CONFIRMATION = "DELETE_ALL_EXCEPT_WJM"
PRESERVED_TABLES = {
    "alembic_version",
    "users",
    "roles",
    "permissions",
    "role_permissions",
    "user_roles",
    "super_users",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    database_url = settings.DATABASE_URL.lower()
    if "localhost" in database_url or "127.0.0.1" in database_url:
        fail("Refusing to reset a local database. Configure the Render DATABASE_URL first.")
    if not database_url.startswith("postgresql"):
        fail("This reset script supports PostgreSQL only.")
    if os.getenv("CONFIRM_DATABASE_RESET") != CONFIRMATION:
        fail(
            "Destructive reset not confirmed. Set "
            f"CONFIRM_DATABASE_RESET={CONFIRMATION} for this one command."
        )

    inspector = inspect(engine)
    all_tables = set(inspector.get_table_names(schema="public"))
    missing = {"users", "roles", "user_roles", "super_users"} - all_tables
    if missing:
        fail(f"Required authentication tables are missing: {sorted(missing)}")

    with engine.begin() as connection:
        protected = connection.execute(
            text("SELECT id, email, is_active FROM users WHERE LOWER(email) = :email"),
            {"email": PROTECTED_EMAIL},
        ).mappings().first()
        if not protected:
            fail(f"Protected SuperUser {PROTECTED_EMAIL} does not exist.")

        protected_user_id = protected["id"]
        super_role_id = connection.execute(
            text("SELECT id FROM roles WHERE name = 'SuperUser'")
        ).scalar_one_or_none()
        if super_role_id is None:
            fail("The SuperUser role does not exist.")

        # Remove all business/transaction/staff tables first. CASCADE safely clears
        # dependent records while the protected authentication records remain.
        reset_tables = sorted(all_tables - PRESERVED_TABLES)
        if reset_tables:
            quoted = ", ".join(f'\"{name}\"' for name in reset_tables)
            connection.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))

        # Keep only the protected account and only its SuperUser authorization.
        connection.execute(text("DELETE FROM super_users WHERE user_id <> :uid"), {"uid": protected_user_id})
        connection.execute(text("DELETE FROM user_roles WHERE user_id <> :uid"), {"uid": protected_user_id})
        connection.execute(text("DELETE FROM user_roles WHERE user_id = :uid AND role_id <> :rid"), {"uid": protected_user_id, "rid": super_role_id})
        connection.execute(text("DELETE FROM users WHERE id <> :uid"), {"uid": protected_user_id})

        connection.execute(
            text("UPDATE users SET is_active = TRUE, email = :email WHERE id = :uid"),
            {"uid": protected_user_id, "email": PROTECTED_EMAIL},
        )
        connection.execute(
            text("""
                INSERT INTO user_roles (user_id, role_id)
                SELECT :uid, :rid
                WHERE NOT EXISTS (
                    SELECT 1 FROM user_roles WHERE user_id = :uid AND role_id = :rid
                )
            """),
            {"uid": protected_user_id, "rid": super_role_id},
        )
        connection.execute(
            text("""
                INSERT INTO super_users (user_id, notes, created_at, updated_at)
                SELECT :uid, 'Protected Martinsdirect SuperUser', NOW(), NOW()
                WHERE NOT EXISTS (SELECT 1 FROM super_users WHERE user_id = :uid)
            """),
            {"uid": protected_user_id},
        )

        counts = connection.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM users) AS users,
                (SELECT COUNT(*) FROM franchise_users) AS franchises,
                (SELECT COUNT(*) FROM manager_users) AS managers,
                (SELECT COUNT(*) FROM employee_users) AS employees
        """)).mappings().one()

    print("DATABASE RESET COMPLETE")
    print("Protected SuperUser:", PROTECTED_EMAIL)
    print("users:", counts["users"])
    print("franchises:", counts["franchises"])
    print("managers:", counts["managers"])
    print("employees:", counts["employees"])


if __name__ == "__main__":
    main()
