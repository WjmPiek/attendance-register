"""Remove unused outside placeholders shadowed by signed linked branches."""
import json
import re
import unicodedata
from datetime import datetime
from alembic import op
from sqlalchemy import text, inspect

revision = '023_remove_duplicate_branches'
down_revision = '022_commission_document_register'
branch_labels = None
depends_on = None


def key(value):
    value=re.sub(r'\s*\((?:F|C)\)\s*$','',value or '',flags=re.I)
    value=unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower()
    return ' '.join(w for w in re.sub(r'[^a-z0-9 ]',' ',value).split() if w not in {'martin','martins','s','funeral','funerals'})


def cleanup(bind):
    rows=bind.execute(text('SELECT b.*,x.branch_id AS outside_id FROM attendance_branches b LEFT JOIN external_commission_branches x ON x.branch_id=b.id')).mappings().all()
    inspector=inspect(bind)
    references=[(table,fk['constrained_columns'][0]) for table in inspector.get_table_names()
                for fk in inspector.get_foreign_keys(table) if fk['referred_table']=='attendance_branches' and table!='external_commission_branches']
    references=list(set(references+[(table,'branch_id') for table in ('employee_branch_assignments','employee_commission_branch_options','employee_commission_branch_overrides')]+[('commission_entries','earning_branch_id')]))
    removed=[]
    for old in rows:
        linked=[b for b in rows if b['franchise_user_id']==old['franchise_user_id'] and b['is_active'] and b['main_franchise_id'] is not None and not b['outside_id'] and key(b['name'])==key(old['name'])]
        if not old['outside_id'] or len(linked)!=1:
            continue
        # Never discard a staff assignment, rate, document or financial reference.
        used=any(bind.execute(text(f'SELECT 1 FROM "{table}" WHERE "{column}"=:id LIMIT 1'),{'id':old['id']}).scalar() for table,column in references)
        used=used or bind.execute(text('SELECT 1 FROM receipt_commission_settings WHERE franchise_user_id=:fid AND branch_id=:id'),{'fid':old['franchise_user_id'],'id':old['id']}).scalar()
        for doc in bind.execute(text('SELECT source_data FROM commission_documents WHERE franchise_user_id=:fid'),{'fid':old['franchise_user_id']}).scalars():
            data=json.loads(doc)
            used=used or data.get('earning_branch_id')==old['id'] or data.get('external_branch_id')==old['id'] or (not data.get('earning_branch_id') and key(data.get('branch'))==key(old['name']))
        if used:
            continue
        bind.execute(text('INSERT INTO audit_logs(actor_user_id,action,entity_type,entity_id,franchise_user_id,old_values,new_values,note,created_at) VALUES(NULL,:action,:entity,:id,:fid,:old,:new,:note,:now)'),
                     {'action':'unused_duplicate_branch_removed','entity':'attendance_branches','id':str(old['id']),'fid':old['franchise_user_id'],'old':json.dumps(dict(old),default=str),'new':json.dumps({'canonical_branch_id':linked[0]['id']}),'note':'Removed unused outside placeholder after the same branch was linked to this holder. Staff, documents and financial records retained.','now':datetime.utcnow()})
        bind.execute(text('DELETE FROM external_commission_branches WHERE branch_id=:id'),{'id':old['id']})
        bind.execute(text('DELETE FROM attendance_branches WHERE id=:id'),{'id':old['id']})
        removed.append(old['id'])
    return removed


def upgrade():
    cleanup(op.get_bind())


def downgrade():
    pass  # Keep audit snapshots; do not recreate ambiguous branch choices.
