import importlib.util
import json
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services.receipt_commissions import parse_receipt_text, require_payment_proof
from tests.test_mortuary_book import database, record, import_payload, quote_and_import
from tests.test_receipt_commissions import RECEIPT, configure, stage_invoice, stage_receipt
from tests.test_multipage_imports import pdf

spec=importlib.util.spec_from_file_location('wrapped_name_migration',Path(__file__).parents[1]/'alembic/versions/027_wrapped_receipt_name.py')
migration=importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.mark.parametrize('newline',['\n','\r\n'])
def test_receipt_reads_wrapped_surname_without_purchaser_or_id(newline):
    source=RECEIPT.replace('Deceased: Example Person','Deceased: Example Middle\nSurname').replace('Inv No.', 'Buyer Name\nInv No.')
    parsed=parse_receipt_text(source.replace('\n',newline))
    assert parsed['deceased']=='Example Middle Surname'
    assert parsed['id_number']=='0000000000000'


def test_receipt_without_id_boundary_does_not_invent_surname_from_purchaser():
    source=RECEIPT.replace('ID Num: 0000000000000','\nBuyer Name')
    assert parse_receipt_text(source)['deceased']=='Example Person'


def setup_repair(db, *, name='Example Person Surname', changed_amount=False, corrupt_pdf=False):
    configure(db)
    quote_and_import(db,import_payload([dict(record(),deceased=name)]))
    content=pdf(RECEIPT.replace('Deceased: Example Person','Deceased: Example Person\nSurname'))
    digest=sha256(content).hexdigest()
    parsed=parse_receipt_text(RECEIPT)
    old={**parsed,'deceased':'Example Person','page':1,'pages':[1],'filename':'receipt.pdf','source_hash':digest}
    stage_invoice(db,{**old,'deceased':name})
    result=stage_receipt(db,[old],people=())
    doc_id=result['document_ids'][0]
    db.execute(text('INSERT INTO commission_document_files(franchise_user_id,source_hash,filename,file_content) VALUES(2,:hash,:name,:content)'),{'hash':digest,'name':'receipt.pdf','content':content+b'changed' if corrupt_pdf else content})
    if changed_amount:
        old['gross_received']='1.00'
        db.execute(text('UPDATE commission_documents SET source_data=:data WHERE id=:id'),{'data':json.dumps(old),'id':doc_id})
    db.commit()
    return doc_id


def test_repair_reparses_original_pdf_preserves_money_and_identity_and_is_idempotent(database):
    doc_id=setup_repair(database)
    with pytest.raises(HTTPException,match='name and surname'):
        require_payment_proof(database,2,101,'TEST1315')
    before=dict(database.execute(text('SELECT * FROM commission_documents WHERE id=:id'),{'id':doc_id}).mappings().one())
    assert migration.repair_receipt_name(database,2,'TEST1315','TEST-1492')==1
    assert migration.repair_receipt_name(database,2,'TEST1315','TEST-1492')==0
    after=dict(database.execute(text('SELECT * FROM commission_documents WHERE id=:id'),{'id':doc_id}).mappings().one())
    old,new=json.loads(before.pop('source_data')),json.loads(after.pop('source_data'))
    assert before==after
    assert new=={**old,'deceased':'Example Person Surname'}
    assert require_payment_proof(database,2,101,'TEST1315')['invoice_number']=='1309'
    assert database.execute(text("SELECT COUNT(*) FROM audit_logs WHERE action='receipt_wrapped_name_reparsed'")).scalar()==1


@pytest.mark.parametrize('changes',[{'name':'Different Person'},{'changed_amount':True},{'corrupt_pdf':True}])
def test_repair_does_not_override_real_mismatches_or_changed_financial_values(database,changes):
    setup_repair(database,**changes)
    assert migration.repair_receipt_name(database,2,'TEST1315','TEST-1492')==0


def test_repair_is_scoped_to_holder_and_receipt_number(database):
    setup_repair(database)
    assert migration.repair_receipt_name(database,99,'TEST1315','TEST-1492')==0
    assert migration.repair_receipt_name(database,2,'TEST1315','OTHER')==0
