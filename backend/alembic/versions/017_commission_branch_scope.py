"""Keep employee category eligibility and earnings separate for each branch."""
import json
import re
import unicodedata
from alembic import op
from sqlalchemy import text

revision = '017_commission_branch_scope'
down_revision = '016_receipt_commissions'
branch_labels = None
depends_on = None


def _key(value):
    value = re.sub(r'\s*\((?:F|C)\)\s*$', '', value or '', flags=re.I)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return ' '.join(w for w in re.sub(r'[^a-z0-9 ]', ' ', value).split() if w not in {'martin','martins','s','funeral','funerals'})


def upgrade():
    op.execute('''CREATE TABLE employee_commission_branch_options (
        franchise_user_id INTEGER NOT NULL REFERENCES franchise_users(id),
        employee_user_id INTEGER NOT NULL REFERENCES users(id),
        commission_type VARCHAR(40) NOT NULL,
        branch_id INTEGER NOT NULL REFERENCES attendance_branches(id),
        rate NUMERIC(12,4) NULL,
        PRIMARY KEY(franchise_user_id,employee_user_id,commission_type,branch_id))''')
    # Existing enabled categories start in the employee's recorded home branch.
    # The holder explicitly adds other branch/category permissions in the editor.
    op.execute('''INSERT INTO employee_commission_branch_options
        SELECT o.franchise_user_id,o.employee_user_id,o.commission_type,a.branch_id,o.rate
        FROM employee_commission_options o JOIN employee_branch_assignments a
        ON a.employee_user_id=o.employee_user_id AND a.franchise_user_id=o.franchise_user_id
        WHERE o.enabled=TRUE''')
    op.execute('ALTER TABLE commission_entries ADD COLUMN earning_branch_id INTEGER NULL REFERENCES attendance_branches(id)')
    op.execute('CREATE INDEX ix_commission_earning_branch_month ON commission_entries(franchise_user_id,earning_branch_id,service_date)')
    bind = op.get_bind()
    branches = bind.execute(text('SELECT id,franchise_user_id,name FROM attendance_branches')).mappings().all()
    rows = bind.execute(text('''SELECT c.id,c.franchise_user_id,c.branch_name,c.source_metadata,a.branch_id
        FROM commission_entries c LEFT JOIN employee_branch_assignments a ON a.employee_user_id=c.employee_user_id''')).mappings().all()
    for row in rows:
        metadata = json.loads(row['source_metadata'] or '{}')
        key = _key(metadata.get('branch') or row['branch_name'])
        matches = [b['id'] for b in branches if b['franchise_user_id']==row['franchise_user_id'] and _key(b['name'])==key]
        branch_id = matches[0] if len(matches)==1 else row['branch_id']
        if branch_id:
            bind.execute(text('UPDATE commission_entries SET earning_branch_id=:branch WHERE id=:id'), {'branch':branch_id,'id':row['id']})


def downgrade():
    pass  # Preserve historical financial allocations.
