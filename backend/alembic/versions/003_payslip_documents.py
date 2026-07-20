from alembic import op
import sqlalchemy as sa

revision = '003_payslip_documents'
down_revision = '002_employee_number'

def upgrade():
    op.create_table(
        'payslip_documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_user_id', sa.Integer(), nullable=False),
        sa.Column('employee_number', sa.String(100), nullable=True),
        sa.Column('original_filename', sa.Text(), nullable=True),
        sa.Column('stored_filename', sa.Text(), nullable=True),
        sa.Column('file_path', sa.Text(), nullable=True),
    )

def downgrade():
    op.drop_table('payslip_documents')
