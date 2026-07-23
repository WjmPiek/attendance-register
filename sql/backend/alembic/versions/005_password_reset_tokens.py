from alembic import op
import sqlalchemy as sa

revision = "005_password_reset_tokens"
down_revision = "004_stabilization_v2"
branch_labels = None
depends_on = None

def upgrade():
    bind=op.get_bind(); inspector=sa.inspect(bind)
    if "password_reset_tokens" not in inspector.get_table_names():
        op.create_table("password_reset_tokens",
          sa.Column("id",sa.Integer(),primary_key=True),
          sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
          sa.Column("token_hash",sa.String(64),nullable=False,unique=True),
          sa.Column("expires_at",sa.DateTime(),nullable=False),
          sa.Column("used_at",sa.DateTime(),nullable=True),
          sa.Column("created_at",sa.DateTime(),server_default=sa.text("CURRENT_TIMESTAMP"),nullable=False))
        op.create_index("ix_password_reset_tokens_user_id","password_reset_tokens",["user_id"])

def downgrade():
    op.drop_table("password_reset_tokens")
