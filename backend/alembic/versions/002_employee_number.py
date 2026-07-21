from alembic import op
import sqlalchemy as sa


revision = "002_employee_number"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {
        column["name"]
        for column in inspector.get_columns("employee_users")
    }

    if "employee_number" not in columns:
        op.add_column(
            "employee_users",
            sa.Column(
                "employee_number",
                sa.String(length=100),
                nullable=True,
            ),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {
        column["name"]
        for column in inspector.get_columns("employee_users")
    }

    if "employee_number" in columns:
        op.drop_column("employee_users", "employee_number")