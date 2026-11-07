from datetime import datetime, date
from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import text

from app.api import commission
from app.services import commission_automation as auto, email_service
from app.services.commission_carry_forward import carry_info
from tests.test_commission_automation import delivery_db
from tests.test_mortuary_book import database
from tests.test_commission_payment_proof import manual_setup, payload
from tests.test_service_claims import STAFF, evidence


def setup(db,monkeypatch):
    manual_setup(db)
    claim=commission.create_entry(payload(),STAFF,db)
    delivered=[]
    def send(email,subject,message,**kwargs):
        delivered.append((subject,kwargs['attachments'][0][1]))
        return 'sent',datetime(2026,11,25,17),None,{}
    monkeypatch.setattr(email_service,'send_smtp_email',send)
    return claim,delivered


def cycle(db,month):
    year,number=map(int,month.split('-'))
    previous=datetime(year,number,1).date()
    from datetime import timedelta
    first=(previous-timedelta(days=1)).replace(day=26)
    return commission.entries(employee_user_id=11,from_date=first,to_date=date(year,number,25),current_user=STAFF,db=db)


def test_missing_documents_carry_to_next_month_then_approve_in_that_month_once(delivery_db,monkeypatch):
    db=delivery_db;claim,delivered=setup(db,monkeypatch)
    auto.send_due_reports(db,2,datetime(2026,11,25,17))
    auto.send_due_reports(db,2,datetime(2026,11,25,17,1))
    assert len(delivered)==1
    assert cycle(db,'2026-11')['items']==[]
    next_month=cycle(db,'2026-12')
    assert next_month['total']==0 and next_month['items'][0]['status']=='pending'
    assert next_month['items'][0]['carried_from_month']=='2026-11'
    assert next_month['branch_category_totals'][0]['pending_total']==Decimal(100)
    assert db.execute(text("SELECT COUNT(*) FROM notifications WHERE subject='Commission carried forward'")).scalar()==2
    pdf='\n'.join(p.extract_text() for p in PdfReader(BytesIO(delivered[0][1])).pages)
    assert 'TOTAL APPROVED FOR FINANCE: R 0.00' in ' '.join(pdf.split())
    assert 'Carried over from November 2026 into December 2026.' in ' '.join(pdf.split())
    evidence(db)
    assert auto.auto_approve_holder(db,2)>=1
    db.commit()
    assert auto.auto_approve_holder(db,2)==0
    approved=cycle(db,'2026-12')
    assert approved['total']==100 and approved['items'][0]['service_date']=='2026-11-02'
    assert approved['items'][0]['carry_forward_notice'].startswith('Carried over from November')
    notice=db.execute(text("SELECT message FROM notifications WHERE related_id=:id AND subject='Commission automatically approved' ORDER BY id DESC"),{'id':claim['id']}).scalar()
    assert 'Carried over from November 2026 into December 2026' in notice
    auto.send_due_reports(db,2,datetime(2026,12,25,17))
    dec_pdf='\n'.join(p.extract_text() for p in PdfReader(BytesIO(delivered[-1][1])).pages)
    assert 'Carried over from November 2026 into December 2026' in ' '.join(dec_pdf.split())
    assert db.execute(text('SELECT COUNT(*) FROM commission_monthly_report_items WHERE entry_id=:id'),{'id':claim['id']}).scalar()==1
    auto.send_due_reports(db,2,datetime(2027,1,25,17))
    january=auto.report_content(db,2,db.execute(text("SELECT * FROM commission_monthly_reports WHERE month_key='2027-01'")).mappings().one())[0]
    assert not any(r['id']==claim['id'] for r in january)


def test_missing_documents_roll_over_each_month_with_one_notice_per_cycle(delivery_db,monkeypatch):
    db=delivery_db;claim,_=setup(db,monkeypatch)
    for moment in [datetime(2026,11,25,17),datetime(2026,12,25,17),datetime(2026,12,26,8)]:
        auto.send_due_reports(db,2,moment)
    assert db.execute(text('SELECT COUNT(*) FROM commission_carry_forwards')).scalar()==2
    assert db.execute(text("SELECT COUNT(*) FROM notifications WHERE subject='Commission carried forward'")).scalar()==4
    assert cycle(db,'2026-12')['items']==[]
    row=cycle(db,'2027-01')['items'][0]
    assert row['carried_from_month']=='2026-12' and row['carried_to_month']=='2027-01'
    assert not row['payment_eligible'] and row['status']=='pending'


def test_failed_old_email_retry_cannot_pull_carried_claim_back_into_old_month(delivery_db,monkeypatch):
    db=delivery_db;claim,_=setup(db,monkeypatch)
    monkeypatch.setattr(email_service,'send_smtp_email',lambda *a,**kw:('failed',None,'SMTP unavailable',{}))
    auto.send_due_reports(db,2,datetime(2026,11,25,17))
    evidence(db);auto.auto_approve_holder(db,2);db.commit()
    sent=[]
    monkeypatch.setattr(email_service,'send_smtp_email',lambda *a,**kw:(sent.append(kw['attachments'][0][1]) or ('sent',datetime(2026,11,25,18),None,{})))
    auto.send_due_reports(db,2,datetime(2026,11,25,18))
    assert db.execute(text('SELECT COUNT(*) FROM commission_monthly_report_items WHERE entry_id=:id'),{'id':claim['id']}).scalar()==0
    assert cycle(db,'2026-12')['total']==100
    assert db.execute(text("SELECT COUNT(*) FROM notifications WHERE subject='Commission carried forward'")).scalar()==2


def test_cancelled_carried_claim_is_not_rolled_again_or_included_in_payment(delivery_db,monkeypatch):
    db=delivery_db;claim,_=setup(db,monkeypatch)
    auto.send_due_reports(db,2,datetime(2026,11,25,17))
    db.execute(text("UPDATE commission_entries SET status='cancelled',is_cancelled=TRUE WHERE id=:id"),{'id':claim['id']});db.commit()
    auto.send_due_reports(db,2,datetime(2026,12,25,17))
    assert carry_info(db,claim['id'])['carried_to_month']=='2026-12'
    assert db.execute(text('SELECT COUNT(*) FROM commission_carry_forwards')).scalar()==1
    assert cycle(db,'2026-12')['total']==0


@pytest.mark.parametrize('verified',[False,True])
def test_claim_submitted_after_report_closed_enters_new_cycle_immediately(delivery_db,monkeypatch,verified):
    db=delivery_db
    manual_setup(db)
    monkeypatch.setattr(email_service,'send_smtp_email',lambda *a,**kw:('sent',datetime(2026,11,25,17),None,{}))
    auto.send_due_reports(db,2,datetime(2026,11,25,17))
    if verified: evidence(db)
    saved=commission.create_entry(payload(),STAFF,db)
    result=cycle(db,'2026-12')
    assert any(r['id']==saved['id'] for r in result['items'])
    assert cycle(db,'2026-11')['items']==[]
    assert result['total']==(100 if verified else 0)
    assert carry_info(db,saved['id'])['carried_to_month']=='2026-12'
