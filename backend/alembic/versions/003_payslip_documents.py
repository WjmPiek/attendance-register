from alembic import op
import sqlalchemy as sa

revision = '003_payslip_documents'
down_revision = '002_employee_number'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if 'payslip_documents' not in inspector.get_table_names():
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
    inspector = sa.inspect(op.get_bind())
    if 'payslip_documents' in inspector.get_table_names():
        op.drop_table('payslip_documents')
