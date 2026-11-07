from datetime import datetime
from decimal import Decimal
from io import BytesIO
import json

import pytest
from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import text

from app.api import commission, mortuary, receipt_commissions as imports
from app.services import commission_automation as auto, email_service
from app.services.receipt_commissions import save_branch_options
from tests.test_mortuary_book import database, record
from tests.test_receipt_commissions import configure, receipt, stage_invoice, stage_receipt, OWNER
from tests.test_service_claims import STAFF
from tests.test_commission_payment_proof import payload
from tests.test_commission_automation import delivery_db


def book(db, source=None):
    token=mortuary.signer().dumps({'kind':'preview','user_id':1,'franchise_user_id':2,'records':[source or record()]})
    return mortuary.stage_evidence(mortuary.EvidenceIn(preview_token=token,confirmed_franchise=True),OWNER,db)


def claim(category='invoice_commission', **changes):
    return payload().model_copy(update={'commission_type':category,**changes})


def test_uploads_save_no_recipients_and_never_award_every_enabled_person(database):
    configure(database)
    book(database)
    token=imports.signer().dumps({'kind':'receipts','user_id':1,'franchise_user_id':2,'records':[receipt()]})
    imports.stage(imports.StageIn(preview_token=token,confirmed_franchise=True),OWNER,database)
    stage_invoice(database)
    assert database.execute(text('SELECT COUNT(*) FROM commission_document_staff')).scalar()==0
    assert auto.auto_approve_holder(database,2)==0
    assert database.execute(text('SELECT COUNT(*) FROM commission_entries')).scalar()==0
    saved=commission.create_entry(claim(),STAFF,database)
    assert saved['status']=='approved'
    assert Decimal(str(saved['calculated_amount']))==Decimal('410.10')
    assert saved['employee_user_id']==11 and saved['earning_branch_id']==101
    assert Decimal(str(saved['invoice_value_before_tax']))==Decimal('20504.88')
    totals=commission.entries(current_user=STAFF,db=database)['branch_category_totals']
    invoice_total=next(t for t in totals if t['commission_type']=='invoice_commission')
    assert invoice_total['branch_id']==101 and invoice_total['approved_total']==Decimal('410.10')
    assert auto.auto_approve_holder(database,2)==0


def test_invoice_claim_before_uploads_reconciles_after_final_instalment(database):
    configure(database)
    saved=commission.create_entry(claim(),STAFF,database)
    assert saved['status']=='pending' and saved['calculated_amount']==0
    book(database);stage_invoice(database,total='1150.00')
    stage_receipt(database,[dict(receipt(),gross_received='500.00')],people=(),with_invoice=False)
    assert auto.auto_approve_holder(database,2)==0
    row=commission.entries(current_user=STAFF,db=database)['items'][0]
    assert not row['payment_eligible'] and Decimal(row['expected_amount'])==20
    stage_receipt(database,[dict(receipt(),receipt_number='SECOND',gross_received='650.00')],people=(),with_invoice=False)
    assert auto.auto_approve_holder(database,2)==1
    database.commit()
    assert auto.auto_approve_holder(database,2)==0
    assert database.execute(text('SELECT status FROM commission_entries WHERE id=:id'),{'id':saved['id']}).scalar()=='approved'
    with pytest.raises(HTTPException,match='already has'):
        commission.create_entry(claim(),STAFF,database)


@pytest.mark.parametrize('change',[{'claim_deceased':'Other Person'},{'reference':'OTHER'},{'earning_branch_id':102}])
def test_identity_or_branch_mismatch_never_approves(database,change):
    configure(database);book(database);stage_receipt(database,people=())
    saved=commission.create_entry(claim(**change),STAFF,database)
    assert saved['status']=='pending'
    assert auto.auto_approve_holder(database,2)==0


def test_removal_claim_checks_printed_staff_role_and_hours(database):
    configure(database);book(database);stage_receipt(database,people=())
    good=commission.create_entry(claim('removals'),STAFF,database)
    assert good['status']=='approved' and Decimal(str(good['calculated_amount']))>0
    assert json.loads(good['source_metadata'])['fee_label']
    # Another staff member cannot claim the employee role by selecting a fee.
    other=type(STAFF)(id=12)
    wrong=commission.create_entry(claim('removals'),other,database)
    assert wrong['employee_user_id']==12 and wrong['status']=='pending'
    assert 'role' in wrong['notice']


def test_disabled_category_cannot_be_claimed(database):
    configure(database)
    save_branch_options(database,2,11,{101:{'enabled_types':['removals']}},1)
    with pytest.raises(HTTPException,match='not enabled'):
        commission.create_entry(claim(),STAFF,database)


def test_registered_outside_branch_detected_without_manual_selection(database):
    result=imports.declare_external_branch(imports.ExternalBranchIn(name='Outside Example'),OWNER,database)
    bid=result['id'] if 'id' in result else result['branch_id']
    assert imports.check_import_branch(database,2,{'branch':'Outside Example'})==bid
    with pytest.raises(HTTPException):
        imports.check_import_branch(database,99,{'branch':'Outside Example'})


def test_email_envelope_and_pdf_attachment_include_both_recipients(monkeypatch):
    config=email_service.EmailConfig('smtp.example.com',587,'sender@example.com','test-only-password',
        'sender@example.com','Test',True,False,10,'test')
    monkeypatch.setattr(email_service,'get_email_config',lambda:config)
    delivered=[]
    class FakeSMTP:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def ehlo(self): pass
        def starttls(self,**kwargs): pass
        def login(self,*args): pass
        def send_message(self,message,**kwargs):
            delivered.append((message,kwargs['to_addrs']))
            return {}
    monkeypatch.setattr(email_service.smtplib,'SMTP',FakeSMTP)
    result=email_service.send_smtp_email(auto.FINANCE_RECIPIENTS,'Test statement','Test only',
        attachments=[('statement.pdf',b'%PDF-test','application/pdf')])
    assert result[0]=='sent'
    message,recipients=delivered[0]
    assert recipients==['wjm@martinsdirect.com','finance@martinsdirect.com']
    attachment=list(message.iter_attachments())[0]
    assert attachment.get_filename()=='statement.pdf'
    assert attachment.get_content_type()=='application/pdf'
    assert attachment.get_payload(decode=True)==b'%PDF-test'


def test_automatic_monthly_pdf_uses_both_recipients_without_settings(delivery_db,monkeypatch):
    db=delivery_db;configure(db)
    commission.create_entry(claim(),STAFF,db)  # pending: no documents
    book(db);stage_receipt(db,people=())
    auto.auto_approve_holder(db,2);db.commit()
    # A second category remains blocked and must not enter the approved total.
    save_branch_options(db,2,11,{101:{'enabled_types':['invoice_commission','overtime'],'rates':{'driver_overtime':'75'}}},1);db.commit()
    commission.create_entry(claim('overtime',reference='MISSING'),STAFF,db)
    sent=[]
    def send(email,subject,message,**kwargs):
        sent.append((email,kwargs['attachments']))
        return 'sent',datetime(2026,11,25,17),None,{}
    monkeypatch.setattr(email_service,'send_smtp_email',send)
    auto.send_due_reports(db,2,datetime(2026,11,25,16,59))
    assert sent==[]
    auto.send_due_reports(db,2,datetime(2026,11,25,17))
    auto.send_due_reports(db,2,datetime(2026,11,25,17,1))
    assert len(sent)==1 and sent[0][0]==auto.FINANCE_RECIPIENTS
    filename,pdf,mime=sent[0][1][0]
    assert filename.endswith('.pdf') and mime=='application/pdf'
    content='\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
    assert 'TOTAL APPROVED FOR FINANCE: R 410.10' in content
    assert 'PENDING - NOT APPROVED FOR PAYMENT' in content and 'MISSING' in content
    assert 'MF File Receipts' in content and 'EXAMPLE' in content
    assert 'Approved totals by manager / employee - all service branches' in content
    report=db.execute(text('SELECT * FROM commission_monthly_reports')).mappings().one()
    assert report['pdf_content']==pdf
    assert str(report['period_start'])=='2026-10-26'
    assert commission.monthly_statement(report['id'],current_user=OWNER,db=db).body==pdf
    with pytest.raises(HTTPException):
        commission.monthly_statement(report['id'],current_user=STAFF,db=db)
