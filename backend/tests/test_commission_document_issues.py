from app.services.commission_document_issues import document_issues

def test_missing_evidence_links_to_each_missing_import():
    issues=document_issues([{'id':1,'kind':'mortuary'}],False,'Missing evidence')
    assert [(i['action'],i['kind']) for i in issues]==[('upload','invoice'),('upload','receipt')]

def test_fully_uploaded_mismatch_links_to_evidence_and_paid_folder_has_no_issues():
    docs=[{'id':1,'kind':'mortuary'},{'id':2,'kind':'invoice'},{'id':3,'kind':'receipt'}]
    assert document_issues(docs,False,'Receipt invoice number does not match')[0]['document_ids']==[2,3]
    assert document_issues(docs,False,'Deceased name must match')[0]['document_ids']==[1,2,3]
    assert document_issues(docs,True,'Complete')==[]

def test_invalid_main_vat_points_to_main_record_and_invoice():
    docs=[{'id':1,'kind':'mortuary'},{'id':2,'kind':'invoice'},{'id':3,'kind':'receipt'}]
    issue=document_issues(docs,False,'The system branch VAT number is invalid.')[0]
    assert issue['action']=='main_vat' and issue['document_ids']==[2]
