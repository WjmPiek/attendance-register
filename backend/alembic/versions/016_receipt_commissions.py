"""Employee opt-ins and matched receipt/book commission evidence."""
from alembic import op

revision = '016_receipt_commissions'
down_revision = '015_mortuary_book'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE attendance_branches (
        id SERIAL PRIMARY KEY, franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        main_franchise_id INTEGER NULL, name VARCHAR(255) NOT NULL, vat_number VARCHAR(100) NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE, main_synced BOOLEAN NOT NULL DEFAULT FALSE,
        UNIQUE(franchise_user_id,main_franchise_id))''')
    op.execute('''CREATE TABLE employee_branch_assignments (
        franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        employee_user_id INTEGER PRIMARY KEY REFERENCES users(id),
        branch_id INTEGER NOT NULL REFERENCES attendance_branches(id),
        can_import_commissions BOOLEAN NOT NULL DEFAULT FALSE)''')
    op.execute('''INSERT INTO attendance_branches(franchise_user_id,name,vat_number)
        SELECT id,COALESCE(NULLIF(franchise_name,''),NULLIF(business_name,''),'Unassigned branch'),vat_number FROM franchise_users''')
    op.execute('''INSERT INTO employee_branch_assignments(franchise_user_id,employee_user_id,branch_id)
        SELECT s.franchise_user_id,s.user_id,b.id FROM
        (SELECT franchise_user_id,user_id FROM employee_users UNION SELECT franchise_user_id,user_id FROM manager_users) s
        JOIN attendance_branches b ON b.franchise_user_id=s.franchise_user_id ON CONFLICT DO NOTHING''')
    op.execute('''CREATE TABLE employee_commission_options (
        franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        employee_user_id INTEGER NOT NULL REFERENCES users(id),
        commission_type VARCHAR(40) NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT FALSE,
        rate NUMERIC(12,4) NULL,
        updated_by_user_id INTEGER NOT NULL REFERENCES users(id),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        PRIMARY KEY(franchise_user_id,employee_user_id,commission_type))''')
    op.execute('''CREATE TABLE receipt_commission_settings (
        franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        branch_id INTEGER NOT NULL DEFAULT 0,
        vat_registered BOOLEAN NOT NULL,
        vat_number VARCHAR(100) NULL,
        vat_rate NUMERIC(7,4) NOT NULL DEFAULT 15,
        receipt_percentage NUMERIC(7,4) NULL,
        updated_by_user_id INTEGER NOT NULL REFERENCES users(id),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        PRIMARY KEY(franchise_user_id,branch_id))''')
    op.execute('''CREATE TABLE commission_documents (
        id SERIAL PRIMARY KEY,
        franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        kind VARCHAR(20) NOT NULL,
        branch_key VARCHAR(255) NOT NULL,
        mf_key VARCHAR(255) NOT NULL,
        document_key VARCHAR(255) NOT NULL,
        source_data TEXT NOT NULL,
        source_hash VARCHAR(64) NOT NULL,
        created_by_user_id INTEGER NOT NULL REFERENCES users(id),
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        UNIQUE(franchise_user_id,kind,branch_key,document_key))''')
    op.execute('''CREATE TABLE commission_document_staff (
        document_id INTEGER NOT NULL REFERENCES commission_documents(id),
        employee_user_id INTEGER NOT NULL REFERENCES users(id),
        removal_role VARCHAR(20) NULL,
        PRIMARY KEY(document_id,employee_user_id))''')
    op.execute('ALTER TABLE commission_entries ADD COLUMN mortuary_document_id INTEGER NULL REFERENCES commission_documents(id)')
    op.execute('ALTER TABLE commission_entries ADD COLUMN receipt_document_id INTEGER NULL REFERENCES commission_documents(id)')
    op.execute('ALTER TABLE commission_entries ADD COLUMN source_metadata TEXT NULL')
    op.execute("CREATE UNIQUE INDEX uq_receipt_employee_award ON commission_entries(receipt_document_id,employee_user_id) WHERE commission_type='invoice_commission' AND receipt_document_id IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_mortuary_employee_award ON commission_entries(mortuary_document_id,employee_user_id) WHERE commission_type='removals' AND mortuary_document_id IS NOT NULL")
    op.execute('CREATE INDEX ix_commission_documents_case ON commission_documents(franchise_user_id,branch_key,mf_key,kind)')
    # Historical approved entries and their amounts stay intact. Retain their source
    # allocations as book evidence so a later receipt cannot pay the removal twice.
    op.execute('''INSERT INTO commission_documents(franchise_user_id,kind,branch_key,mf_key,document_key,source_data,source_hash,created_by_user_id)
        SELECT a.franchise_user_id,'mortuary',a.branch_key,
            REGEXP_REPLACE(REGEXP_REPLACE(UPPER(a.reference_key),'^MF[ -]*',''),'[^A-Z0-9]','','g'),a.reference_key,
            json_build_object('branch',e.branch_name,'reference',e.reference,'service_date',e.service_date,
                'date_in',a.date_in,'time_in',a.time_in,'legacy',true,'notes',e.notes,
                'id_number',substring(e.notes from 'ID Number: ([0-9]+)'))::text,
            MIN(a.source_hash),MIN(e.created_by_user_id)
        FROM mortuary_import_allocations a JOIN commission_entries e ON e.id=a.entry_id
        GROUP BY a.franchise_user_id,a.branch_key,a.reference_key,e.branch_name,e.reference,e.service_date,a.date_in,a.time_in,e.notes
        ON CONFLICT(franchise_user_id,kind,branch_key,document_key) DO NOTHING''')
    op.execute('''UPDATE commission_entries e SET mortuary_document_id=d.id
        FROM mortuary_import_allocations a JOIN commission_documents d
        ON d.franchise_user_id=a.franchise_user_id AND d.kind='mortuary' AND d.branch_key=a.branch_key AND d.document_key=a.reference_key
        WHERE a.entry_id=e.id''')
    op.execute('''INSERT INTO commission_document_staff(document_id,employee_user_id,removal_role)
        SELECT e.mortuary_document_id,e.employee_user_id,a.removal_role
        FROM mortuary_import_allocations a JOIN commission_entries e ON e.id=a.entry_id
        WHERE e.mortuary_document_id IS NOT NULL ON CONFLICT DO NOTHING''')


def downgrade():
    pass  # Keep financial evidence and history.
