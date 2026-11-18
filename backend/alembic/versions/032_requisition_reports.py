"""Monthly card statements and explicit delivery recipients."""

from alembic import op
import sqlalchemy as sa

revision = "032_requisition_reports"
down_revision = "031_requisition_revisions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "requisition_emails",
        sa.Column(
            "recipient",
            sa.String(255),
            nullable=False,
            server_default="wjm@martinsdirect.com",
        ),
    )
    op.add_column(
        "requisition_emails",
        sa.Column(
            "include_workbook", sa.Boolean, nullable=False, server_default=sa.true()
        ),
    )
    op.create_table(
        "requisition_report_settings",
        sa.Column(
            "franchise_user_id",
            sa.Integer,
            sa.ForeignKey("franchise_users.id"),
            primary_key=True,
        ),
        sa.Column("recipient", sa.String(255), nullable=False),
    )
    op.create_table(
        "requisition_monthly_reports",
        sa.Column(
            "month_id",
            sa.Integer,
            sa.ForeignKey("requisition_months.id"),
            primary_key=True,
        ),
        sa.Column(
            "email_id",
            sa.Integer,
            sa.ForeignKey("requisition_emails.id"),
            nullable=False,
        ),
    )


def downgrade():
    raise RuntimeError("Retain monthly report delivery history.")
