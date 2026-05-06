from __future__ import annotations

from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.timezone import now_sa_naive
from app.services.email_service import send_smtp_email


def ensure_notifications_schema(db: Session) -> None:
    """Create/migrate the notification outbox lazily during requests, not at app startup."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NULL,
            recipient_user_id INTEGER NULL,
            franchise_user_id INTEGER NULL,
            recipient_email VARCHAR(255) NULL,
            recipient_number VARCHAR(80) NULL,
            notification_type VARCHAR(80) NOT NULL DEFAULT 'system',
            subject VARCHAR(255) NOT NULL DEFAULT 'Notification',
            message TEXT NOT NULL DEFAULT '',
            status VARCHAR(40) NOT NULL DEFAULT 'pending',
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            severity VARCHAR(40) NOT NULL DEFAULT 'info',
            target_tab VARCHAR(80) NULL,
            related_table VARCHAR(120) NULL,
            related_id INTEGER NULL,
            sent_at TIMESTAMP NULL,
            error_message TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NULL
        )
    """))
    for stmt in [
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_id INTEGER NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS recipient_user_id INTEGER NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS franchise_user_id INTEGER NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS recipient_email VARCHAR(255) NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS recipient_number VARCHAR(80) NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS notification_type VARCHAR(80) NOT NULL DEFAULT 'system'",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS subject VARCHAR(255) NOT NULL DEFAULT 'Notification'",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS message TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS status VARCHAR(40) NOT NULL DEFAULT 'pending'",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS is_read BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS severity VARCHAR(40) NOT NULL DEFAULT 'info'",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS target_tab VARCHAR(80) NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS related_table VARCHAR(120) NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS related_id INTEGER NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS sent_at TIMESTAMP NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS error_message TEXT NULL",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()",
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL",
    ]:
        db.execute(text(stmt))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_notifications_franchise_created
        ON notifications (franchise_user_id, created_at DESC)
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_notifications_recipient_created
        ON notifications (recipient_user_id, created_at DESC)
    """))
    db.commit()


def _send_email_if_configured(recipient_email: str | None, subject: str, message: str) -> tuple[str, datetime | None, str | None]:
    status_value, sent_at, error_message, _diagnostics = send_smtp_email(recipient_email, subject, message)
    return status_value, sent_at, error_message

def create_notification(
    db: Session,
    notification_type: str,
    subject: str,
    message: str,
    recipient_email: str | None = None,
    recipient_number: str | None = None,
    related_table: str | None = None,
    related_id: int | None = None,
    user_id: int | None = None,
    recipient_user_id: int | None = None,
    franchise_user_id: int | None = None,
    severity: str = 'info',
    target_tab: str | None = None,
    send_email: bool = True,
):
    ensure_notifications_schema(db)
    status_value = 'pending'
    sent_at = None
    error_message = None
    if send_email:
        status_value, sent_at, error_message = _send_email_if_configured(recipient_email, subject, message)
    now = now_sa_naive()
    row = db.execute(
        text("""
            INSERT INTO notifications (
                user_id, recipient_user_id, franchise_user_id, recipient_email, recipient_number,
                notification_type, subject, message, status, is_read, severity, target_tab,
                related_table, related_id, sent_at, error_message, created_at, updated_at
            )
            VALUES (
                :user_id, :recipient_user_id, :franchise_user_id, :recipient_email, :recipient_number,
                :notification_type, :subject, :message, :status, FALSE, :severity, :target_tab,
                :related_table, :related_id, :sent_at, :error_message, :created_at, :updated_at
            )
            RETURNING id
        """),
        {
            'user_id': user_id,
            'recipient_user_id': recipient_user_id,
            'franchise_user_id': franchise_user_id,
            'recipient_email': recipient_email,
            'recipient_number': recipient_number,
            'notification_type': notification_type,
            'subject': subject,
            'message': message,
            'status': status_value,
            'severity': severity,
            'target_tab': target_tab,
            'related_table': related_table,
            'related_id': related_id,
            'sent_at': sent_at,
            'error_message': error_message,
            'created_at': now,
            'updated_at': now,
        },
    ).mappings().first()
    db.commit()
    return dict(row) if row else {'id': None}
