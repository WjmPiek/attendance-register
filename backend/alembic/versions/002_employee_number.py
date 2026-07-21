from alembic import op
import sqlalchemy as sa

revision = '002_employee_number'
down_revision = '001_initial'

def upgrade():
    op.add_column(
        'employee_users',
        sa.Column('employee_number', sa.String(length=100), nullable=True)
    )

def downgrade():
    op.drop_column('employee_users', 'employee_number')
