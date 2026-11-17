"""Retain submitted request versions while employees make corrections."""

from alembic import op
import sqlalchemy as sa

revision = "031_requisition_revisions"
down_revision = "030_requisitions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "requisitions",
        sa.Column("revision", sa.Integer, nullable=False, server_default="0"),
    )
    op.execute("UPDATE requisitions SET revision=1 WHERE status='submitted'")
    op.create_table(
        "requisition_revisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "requisition_id",
            sa.Integer,
            sa.ForeignKey("requisitions.id"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("snapshot", sa.Text, nullable=False),
        sa.UniqueConstraint("requisition_id", "revision"),
    )


def downgrade():
    raise RuntimeError("Submitted requisition history must be retained.")
