import importlib.util
import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import pytest
from sqlalchemy import text
from app.services import invoice_proof
from app.services.receipt_commissions import require_payment_proof
from tests.test_invoice_payment_proof import INVOICE
from tests.test_mortuary_book import database,record,import_payload,quote_and_import
from tests.test_multipage_imports import pdf
from tests.test_receipt_commissions import configure,receipt,stage_invoice,stage_receipt

spec=importlib.util.spec_from_file_location('invoice_name_migration',Path(__file__).parents[1]/'alembic/versions/028_invoice_layout_name.py')
migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)


@pytest.mark.parametrize('raw,expected',[('Example Personff','Example Personff'),('Different Name','Example Personf')])
def test_complete_name_requires_exact_plain_text_confirmation(monkeypatch,raw,expected):
    layout=INVOICE.replace('Deceased Name    Example Person','Deceased Name    Example Personf         f')
    page=SimpleNamespace(extract_text=lambda **kw:layout if kw else raw)
    monkeypatch.setattr(invoice_proof,'PdfReader',lambda data:SimpleNamespace(is_encrypted=False,pages=[page]))
    rows,errors=invoice_proof.parse_invoice_pdf(b'%PDF-test')
    assert not errors and rows[0]['deceased']==expected


def setup_repair(db,wrong_name=False,changed_amount=False):
    configure(db)
    name='Example Personff'
    quote_and_import(db,import_payload([dict(record(),deceased=name)]))
    content=pdf(INVOICE.replace('Example Person',name if not wrong_name else 'Different Person'))
    digest=sha256(content).hexdigest()
    source={**invoice_proof.parse_invoice_text(INVOICE.replace('Example Person','Example Personf')),'source_hash':digest,'page':1,'filename':'invoice.pdf'}
    doc_id=stage_invoice(db,source,total=source['invoice_total'])
    stage_receipt(db,[dict(receipt(),deceased=name,gross_received='1150.00')],people=(),with_invoice=False)
    db.execute(text('INSERT INTO commission_document_files(franchise_user_id,source_hash,filename,file_content) VALUES(2,:hash,:name,:content)'),{'hash':digest,'name':'invoice.pdf','content':content})
    if changed_amount:
        data=json.loads(db.execute(text('SELECT source_data FROM commission_documents WHERE id=:id'),{'id':doc_id}).scalar())
        data['invoice_total']='999'
        db.execute(text('UPDATE commission_documents SET source_data=:data WHERE id=:id'),{'id':doc_id,'data':json.dumps(data)})
    db.commit()
    return doc_id


def test_original_pdf_repair_changes_only_name_and_unblocks_matching_evidence(database):
    doc_id=setup_repair(database)
    before=dict(database.execute(text('SELECT * FROM commission_documents WHERE id=:id'),{'id':doc_id}).mappings().one())
    assert migration.repair_invoice_name(database,2,'TEST1315','1309')==1
    assert migration.repair_invoice_name(database,2,'TEST1315','1309')==0
    after=dict(database.execute(text('SELECT * FROM commission_documents WHERE id=:id'),{'id':doc_id}).mappings().one())
    old,new=json.loads(before.pop('source_data')),json.loads(after.pop('source_data'))
    assert before==after and new=={**old,'deceased':'Example Personff'}
    assert require_payment_proof(database,2,101,'TEST1315')
    assert database.execute(text("SELECT COUNT(*) FROM audit_logs WHERE action='invoice_layout_name_reparsed'")).scalar()==1


@pytest.mark.parametrize('changes',[{'wrong_name':True},{'changed_amount':True}])
def test_invoice_repair_keeps_real_identity_and_financial_mismatches_blocked(database,changes):
    setup_repair(database,**changes)
    assert migration.repair_invoice_name(database,2,'TEST1315','1309')==0
