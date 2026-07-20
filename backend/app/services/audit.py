from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


SENSITIVE_KEYS = {"password", "password_hash", "token", "access_token", "refresh_token"}


def _safe_json(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = {
            k: ("***" if str(k).lower() in SENSITIVE_KEYS else v)
            for k, v in value.items()
        }
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def ensure_audit_log_table(db: Session) -> None:
    """Create the audit log table on existing local databases.

    Base.metadata.create_all handles fresh installs. This helper keeps already-created
    SQLite/Postgres databases safe without needing a manual migration step.
    """
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY,
            actor_user_id INTEGER NULL,
            action VARCHAR(80) NOT NULL,
            entity_type VARCHAR(80) NOT NULL,
            entity_id VARCHAR(80) NULL,
            franchise_user_id INTEGER NULL,
            old_values TEXT NULL,
            new_values TEXT NULL,
            request_ip VARCHAR(80) NULL,
            note TEXT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """))


def write_audit_log(
    db: Session,
    *,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | str | None = None,
    franchise_user_id: int | None = None,
    old_values: Any = None,
    new_values: Any = None,
    request_ip: str | None = None,
    note: str | None = None,
) -> None:
    ensure_audit_log_table(db)
    db.execute(text("""
        INSERT INTO audit_logs (
            actor_user_id, action, entity_type, entity_id, franchise_user_id,
            old_values, new_values, request_ip, note, created_at
        ) VALUES (
            :actor_user_id, :action, :entity_type, :entity_id, :franchise_user_id,
            :old_values, :new_values, :request_ip, :note, :created_at
        )
    """), {
        "actor_user_id": actor_user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "franchise_user_id": franchise_user_id,
        "old_values": _safe_json(old_values),
        "new_values": _safe_json(new_values),
        "request_ip": request_ip,
        "note": note,
        "created_at": datetime.utcnow(),
    })
