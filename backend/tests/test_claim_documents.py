from hashlib import sha256
from io import BytesIO
import json
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import text
from app.api import commission,commission_documents
from app.api.deps import get_current_user
from app.db.session import get_db
from app.services.receipt_commissions import save_branch_options
from tests.test_mortuary_book import database
from tests.test_case_claims import setup,claim,evidence
from tests.test_multipage_imports import pdf
from tests.test_receipt_commissions import receipt
from app.api import receipt_commissions


def client_for(db,uid=11):
    app=FastAPI();app.include_router(commission.router,prefix='/commission');app.include_router(commission_documents.router,prefix='/commission-documents')
    app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=uid)
    app.dependency_overrides[get_db]=lambda:db
    return TestClient(app)


def params(**changes):
    return {'earning_branch_id':101,'reference':'MF TEST-1315','commission_type':'invoice_commission','employee_user_id':11,**changes}


def test_staff_can_read_own_claim_documents_without_upload_or_correction_access(database):
    setup(database);claim(database);evidence(database)
    client=client_for(database)
    result=client.get('/commission/case-documents',params=params())
    assert result.status_code==200
    assert {doc['kind'] for doc in result.json()['documents']}=={'mortuary','invoice','receipt'}
    assert result.json()['case']['ready']
    assert client.get('/commission-documents',params={'month':'2026-11'}).status_code==403
    did=result.json()['documents'][0]['id']
    assert client.post(f'/commission-documents/{did}/archive',json={'reason':'Not authorised'}).status_code==403


def test_missing_documents_remain_a_viewable_empty_folder_and_other_months_are_included(database):
    setup(database);claim(database)
    client=client_for(database)
    empty=client.get('/commission/case-documents',params=params())
    assert empty.status_code==200 and empty.json()['documents']==[]
    assert empty.json()['case']['document_counts']=={'mortuary':0,'invoice':0,'receipt':0}
    evidence(database)
    database.execute(text("UPDATE commission_documents SET created_at='2026-01-01' WHERE kind='invoice'"));database.commit()
    assert len(client.get('/commission/case-documents',params=params()).json()['documents'])==3


def test_claim_documents_enforce_staff_branch_category_and_current_permission_scope(database):
    setup(database);claim(database);evidence(database)
    client=client_for(database)
    for changes in [{'employee_user_id':12},{'earning_branch_id':900},{'reference':'OTHER'},{'commission_type':'overtime'},{'franchise_user_id':99}]:
        assert client.get('/commission/case-documents',params=params(**changes)).status_code in (403,404)
    assert client_for(database,12).get('/commission/case-documents',params=params()).status_code==403
    save_branch_options(database,2,11,{101:{'enabled_types':['grave_service'],'rates':{'driver_grave_service':'75'}}},1,branch_id=101);database.commit()
    assert client.get('/commission/case-documents',params=params()).status_code==404
    assert client.get('/commission/case-documents',params=params(commission_type='grave_service')).status_code==200


def store_pdf(db,pages):
    row=dict(db.execute(text("SELECT * FROM commission_documents WHERE kind='invoice'")).mappings().one())
    content=pdf('Selected MF file page','Another MF file private page');digest=sha256(content).hexdigest()
    data=json.loads(row['source_data']);data['pages']=pages
    db.execute(text('UPDATE commission_documents SET source_hash=:hash,source_data=:data WHERE id=:id'),{'hash':digest,'data':json.dumps(data),'id':row['id']})
    db.execute(text('INSERT INTO commission_document_files(franchise_user_id,source_hash,filename,file_content) VALUES(2,:hash,:name,:content)'),{'hash':digest,'name':'batch.pdf','content':content})
    db.commit();return row['id']


def test_pdf_view_keeps_only_selected_document_pages_from_a_batch(database):
    setup(database);claim(database);evidence(database)
    did=store_pdf(database,[1])
    response=client_for(database).get(f'/commission/case-documents/{did}/file',params=params())
    assert response.status_code==200
    reader=PdfReader(BytesIO(response.content))
    assert len(reader.pages)==1 and 'Selected MF file page' in reader.pages[0].extract_text()
    assert 'Another MF file private page' not in reader.pages[0].extract_text()
    assert response.headers['cache-control']=='private, no-store'


def test_pdf_view_preserves_a_two_page_document_and_rejects_unrelated_document_ids(database):
    setup(database);claim(database);evidence(database)
    did=store_pdf(database,[1,2])
    client=client_for(database)
    response=client.get(f'/commission/case-documents/{did}/file',params=params())
    assert response.status_code==200 and len(PdfReader(BytesIO(response.content)).pages)==2
    other,_=receipt_commissions.save_document(database,2,'receipt',dict(receipt(),reference='OTHER',receipt_number='OTHER',source_hash='z'*64),[],1)
    database.commit()
    assert client.get(f'/commission/case-documents/{other}/file',params=params()).status_code==404
