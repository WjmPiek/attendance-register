"""Restricted requisitions, monthly card registers and durable email outbox."""

from alembic import op
import sqlalchemy as sa

revision = "030_requisitions"
down_revision = "029_branch_commission_fees"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "requisition_grants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "franchise_user_id",
            sa.Integer,
            sa.ForeignKey("franchise_users.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("granted_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("franchise_user_id", "user_id"),
    )
    op.create_table(
        "requisition_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "franchise_user_id",
            sa.Integer,
            sa.ForeignKey("franchise_users.id"),
            nullable=False,
        ),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content", sa.LargeBinary, nullable=False),
        sa.UniqueConstraint("franchise_user_id", "sha256"),
    )
    op.create_table(
        "requisition_books",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "franchise_user_id",
            sa.Integer,
            sa.ForeignKey("franchise_users.id"),
            nullable=False,
        ),
        sa.Column("branch_id", sa.Integer, nullable=False, index=True),
        sa.Column("reference", sa.String(255), nullable=False),
        sa.Column("deceased", sa.String(255), nullable=False),
        sa.Column("details", sa.Text, nullable=False),
        sa.Column(
            "source_id",
            sa.Integer,
            sa.ForeignKey("requisition_sources.id"),
            nullable=False,
        ),
        sa.Column("uploaded_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("branch_id", "reference"),
    )
    op.create_table(
        "requisition_months",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "franchise_user_id",
            sa.Integer,
            sa.ForeignKey("franchise_users.id"),
            nullable=False,
        ),
        sa.Column("branch_id", sa.Integer, nullable=False, index=True),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("holder", sa.String(255), nullable=False),
        sa.Column("opening_cents", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("closing_cents", sa.BigInteger),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("branch_id", "month"),
    )
    op.create_table(
        "requisitions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "month_id",
            sa.Integer,
            sa.ForeignKey("requisition_months.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "book_id", sa.Integer, sa.ForeignKey("requisition_books.id"), nullable=False
        ),
        sa.Column("employee_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("employee_name", sa.String(255), nullable=False),
        sa.Column("request_date", sa.Date, nullable=False),
        sa.Column("number", sa.String(100), unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("details", sa.Text, nullable=False),
        sa.Column("lines", sa.Text, nullable=False),
        sa.Column("total_cents", sa.Integer, nullable=False),
        sa.Column("submitted_at", sa.DateTime),
    )
    op.create_table(
        "requisition_transactions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "month_id",
            sa.Integer,
            sa.ForeignKey("requisition_months.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "requisition_id",
            sa.Integer,
            sa.ForeignKey("requisitions.id"),
            nullable=False,
        ),
        sa.Column("client_key", sa.String(36), nullable=False),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("supplier", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_name", sa.String(255), nullable=False),
        sa.Column("receipt_name", sa.String(255), nullable=False),
        sa.Column("receipt_mime", sa.String(80), nullable=False),
        sa.Column("receipt_content", sa.LargeBinary, nullable=False),
        sa.UniqueConstraint("month_id", "client_key"),
    )
    op.create_table(
        "requisition_emails",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "month_id",
            sa.Integer,
            sa.ForeignKey("requisition_months.id"),
            nullable=False,
        ),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("workbook", sa.LargeBinary, nullable=False),
        sa.Column("document", sa.LargeBinary),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("next_attempt_at", sa.DateTime, nullable=False),
        sa.Column("sent_at", sa.DateTime),
    )


def downgrade():
    raise RuntimeError(
        "Requisition financial records must be retained. Restore a reviewed backup to roll back."
    )
