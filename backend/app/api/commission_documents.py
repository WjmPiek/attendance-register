"""Holder and nominated uploader document register, reversible corrections and audit."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import text, bindparam

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.core import User
from app.services.attendance_branches import import_scope
from app.services.receipt_commissions import require_payment_proof, money
from app.services.audit import write_audit_log
from app.services.commission_document_issues import document_issues

router = APIRouter()


def audit(db, user, fid, action, did=None, old=None, new=None, note=None):
    write_audit_log(db, actor_user_id=user.id, franchise_user_id=fid, action=action,
                    entity_type='commission_documents', entity_id=did, old_values=old, new_values=new, note=note)


def document(db, fid, did):
    row=db.execute(text('SELECT * FROM commission_documents WHERE id=:id AND franchise_user_id=:fid'), {'id':did,'fid':fid}).mappings().first()
    if not row: raise HTTPException(404, 'Document not found in this holder group.')
    return row


def serialise(db, row):
    available=bool(db.execute(text('SELECT 1 FROM commission_document_files WHERE franchise_user_id=:fid AND source_hash=:hash'), {'fid':row['franchise_user_id'],'hash':row['source_hash']}).scalar())
    return {k:row[k] for k in ('id','kind','created_at','created_by_user_id','deleted_at','deleted_by_user_id','deletion_reason')} | {
        'record':json.loads(row['source_data']), 'original_available':available}


@router.get('')
def register(month: str = Query(pattern=r'^\d{4}-(0[1-9]|1[0-2])$'), branch_id: int | None = None,
             include_deleted: bool = False, offset: int = Query(default=0,ge=0), limit: int = Query(default=200,ge=1,le=500),
             franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db=Depends(get_db)):
    fid=import_scope(db,current_user,franchise_user_id)
    from app.services.attendance_branches import branches
    from app.services.external_commissions import external_branches
    # Historical evidence stays browsable after a branch is unlinked. The
    # active-branch check below still controls payment readiness.
    choices=[*branches(db,fid,active_only=False),*external_branches(db,fid,active_only=False)]
    if branch_id and branch_id not in {b['id'] for b in choices}: raise HTTPException(403,'Branch is outside this holder group.')
    try:
        year,number=map(int,month.split('-'))
        first=datetime(year,number,1,tzinfo=ZoneInfo('Africa/Johannesburg')).astimezone(timezone.utc).replace(tzinfo=None)
        last=datetime(year+int(number==12),1 if number==12 else number+1,1,tzinfo=ZoneInfo('Africa/Johannesburg')).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError: raise HTTPException(400,'Select a valid upload month.')
    from app.services.receipt_commissions import branch_key
    key=branch_key(next(b['name'] for b in choices if b['id']==branch_id)) if branch_id else None
    where=''' FROM commission_documents d WHERE d.franchise_user_id=:fid AND d.created_at>=:first AND d.created_at<:last '''+(' AND d.deleted_at IS NULL ' if not include_deleted else '')+(' AND d.branch_key=:branch ' if branch_id else '')
    params={'fid':fid,'first':first,'last':last,'branch':key,'limit':limit,'offset':offset}
    total=db.execute(text('SELECT COUNT(*)'+where),params).scalar()
    groups='SELECT d.branch_key,d.mf_key'+where+' GROUP BY d.branch_key,d.mf_key'
    case_total=db.execute(text('SELECT COUNT(*) FROM ('+groups+') grouped_cases'),params).scalar()
    keys=db.execute(text(groups+' ORDER BY MAX(d.created_at) DESC,MAX(d.id) DESC LIMIT :limit OFFSET :offset'),params).all()
    rows=db.execute(text('SELECT d.*'+where+' AND (d.branch_key,d.mf_key) IN :cases ORDER BY d.created_at DESC,d.id DESC').bindparams(bindparam('cases',expanding=True)),
                    {**params,'cases':[tuple(key) for key in keys]}).mappings().all() if keys else []
    cases=[]
    for bk,mf in sorted({(r['branch_key'],r['mf_key']) for r in rows}):
        docs=db.execute(text('SELECT * FROM commission_documents WHERE franchise_user_id=:fid AND branch_key=:branch AND mf_key=:mf AND deleted_at IS NULL ORDER BY id'), {'fid':fid,'branch':bk,'mf':mf}).mappings().all()
        invoices=[json.loads(d['source_data']) for d in docs if d['kind']=='invoice']
        paid=sum((Decimal(str(json.loads(d['source_data']).get('gross_received',0))) for d in docs if d['kind']=='receipt'),Decimal(0))
        invoice_total=Decimal(str(invoices[0]['invoice_total'])) if len(invoices)==1 else None
        b=next((b for b in choices if branch_key(b['name'])==bk),None)
        ready=False;reason='Branch is no longer linked or available.'
        if b and b['is_active']:
            try: require_payment_proof(db,fid,b['id'],mf);ready=True;reason='Documents match and receipts balance the invoice.'
            except HTTPException as exc: reason=exc.detail
        source=json.loads(next(r for r in rows if r['branch_key']==bk and r['mf_key']==mf)['source_data'])
        cases.append({'branch_id':b['id'] if b else None,'branch':b['name'] if b else source.get('branch',bk),'mf':mf,
                      'document_counts':{kind:sum(d['kind']==kind for d in docs) for kind in ('mortuary','invoice','receipt')},
                      'deceased':source.get('deceased'),'reference':source.get('reference',mf),'invoice_total':str(invoice_total) if invoice_total is not None else None,
                      'total_received':str(money(paid)),'balance':str(money(invoice_total-paid)) if invoice_total is not None else None,
                      'ready':ready,'reason':reason,'issues':document_issues(docs,ready,reason),'document_ids':[r['id'] for r in rows if r['branch_key']==bk and r['mf_key']==mf]})
    # Use all cases in this month for the selector, independently of pagination/filter.
    populated=set(db.execute(text('SELECT DISTINCT branch_key FROM commission_documents WHERE franchise_user_id=:fid AND created_at>=:first AND created_at<:last '+('AND deleted_at IS NULL' if not include_deleted else '')),params).scalars())
    result={'branches':[b for b in choices if branch_key(b['name']) in populated],'month':month,'cases':cases,'documents':[serialise(db,r) for r in rows], 'total':total,'case_total':case_total,'offset':offset,'limit':limit}
    audit(db,current_user,fid,'commission_register_viewed',new={'month':month,'branch_id':branch_id,'include_deleted':include_deleted,'offset':offset})
    db.commit()
    return result


@router.get('/case')
def case_documents(branch_id: int, mf: str = Query(min_length=1,max_length=255), include_deleted: bool = False,
                   franchise_user_id: int | None = None,current_user: User = Depends(get_current_user),db=Depends(get_db)):
    """A complete MF folder is independent of upload-month pagination."""
    fid=import_scope(db,current_user,franchise_user_id)
    branch=db.execute(text('SELECT * FROM attendance_branches WHERE id=:id AND franchise_user_id=:fid'),{'id':branch_id,'fid':fid}).mappings().first()
    if not branch:
        raise HTTPException(403,'Branch is outside this holder group.')
    from app.services.receipt_commissions import branch_key,mf_key
    key=mf_key(mf)
    rows=db.execute(text('''SELECT * FROM commission_documents WHERE franchise_user_id=:fid
        AND branch_key=:branch AND mf_key=:mf ORDER BY kind,id'''),
        {'fid':fid,'branch':branch_key(branch['name']),'mf':key}).mappings().all()
    if not rows:
        raise HTTPException(404,'No documents found for this branch and MF File number.')
    active=[r for r in rows if not r['deleted_at']]
    invoices=[json.loads(r['source_data']) for r in active if r['kind']=='invoice']
    total=Decimal(str(invoices[0]['invoice_total'])) if len(invoices)==1 else None
    paid=sum((Decimal(str(json.loads(r['source_data']).get('gross_received',0))) for r in active if r['kind']=='receipt'),Decimal(0))
    ready=False;reason='Branch is no longer linked or available.'
    if branch['is_active']:
        try:
            require_payment_proof(db,fid,branch_id,key)
            ready=True;reason='All three document types match and the invoice is fully paid.'
        except HTTPException as exc: reason=exc.detail
    source=json.loads((active or rows)[0]['source_data'])
    case={'branch_id':branch_id,'branch':branch['name'],'mf':key,'reference':source.get('reference',key),'deceased':source.get('deceased'),
          'ready':ready,'reason':reason,'issues':document_issues(active,ready,reason),'invoice_total':str(total) if total is not None else None,
          'total_received':str(money(paid)),'balance':str(money(total-paid)) if total is not None else None,
          'document_counts':{kind:sum(r['kind']==kind for r in active) for kind in ('mortuary','invoice','receipt')}}
    audit(db,current_user,fid,'commission_mf_folder_viewed',new={'branch_id':branch_id,'mf':key,'include_deleted':include_deleted})
    db.commit()
    return {'case':case,'documents':[serialise(db,r) for r in rows if include_deleted or not r['deleted_at']]}


@router.get('/activity')
def activity(franchise_user_id: int | None = None, document_id: int | None = None, offset: int = Query(default=0,ge=0), current_user: User = Depends(get_current_user), db=Depends(get_db)):
    fid=import_scope(db,current_user,franchise_user_id)
    if document_id: document(db,fid,document_id)
    from app.services.audit import ensure_audit_log_table
    ensure_audit_log_table(db)
    rows=db.execute(text('''SELECT a.*,u.full_name AS actor_name FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_user_id
        WHERE a.franchise_user_id=:fid AND a.entity_type='commission_documents' '''+(' AND a.entity_id=:did ' if document_id else '')+
        ' ORDER BY a.created_at DESC,a.id DESC LIMIT 201 OFFSET :offset'), {'fid':fid,'did':str(document_id),'offset':offset}).mappings().all()
    return {'items':[dict(r) for r in rows[:200]],'has_more':len(rows)>200}


@router.get('/{document_id}')
def detail(document_id: int, franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db=Depends(get_db)):
    fid=import_scope(db,current_user,franchise_user_id);row=document(db,fid,document_id)
    result=serialise(db,row)
    result['staff']=[dict(r) for r in db.execute(text('SELECT s.employee_user_id,s.removal_role,u.full_name FROM commission_document_staff s JOIN users u ON u.id=s.employee_user_id WHERE s.document_id=:id'), {'id':document_id}).mappings()]
    audit(db,current_user,fid,'commission_document_viewed',document_id)
    db.commit();return result


@router.get('/{document_id}/file')
def original(document_id: int, download: bool = False, franchise_user_id: int | None = None, current_user: User = Depends(get_current_user), db=Depends(get_db)):
    fid=import_scope(db,current_user,franchise_user_id);row=document(db,fid,document_id)
    content=db.execute(text('SELECT file_content FROM commission_document_files WHERE franchise_user_id=:fid AND source_hash=:hash'), {'fid':fid,'hash':row['source_hash']}).scalar()
    if content is None: raise HTTPException(404,'This older upload did not retain an original PDF. Its extracted details remain available.')
    audit(db,current_user,fid,'commission_document_downloaded' if download else 'commission_document_pdf_viewed',document_id)
    db.commit()
    return Response(bytes(content),media_type='application/pdf',headers={'Content-Disposition':f'{"attachment" if download else "inline"}; filename="{row["kind"]}-{document_id}.pdf"','Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


class CorrectionIn(BaseModel):
    franchise_user_id: int | None = None
    reason: str = Field(min_length=3,max_length=1000)


@router.post('/{document_id}/archive')
def archive(document_id: int, payload: CorrectionIn, current_user: User = Depends(get_current_user), db=Depends(get_db)):
    fid=import_scope(db,current_user,payload.franchise_user_id)
    if len(payload.reason.strip())<3: raise HTTPException(400,'Enter a reason for deleting this upload.')
    try:
        db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'),{'namespace':15015,'fid':fid})
        row=document(db,fid,document_id)
        if row['deleted_at']: raise HTTPException(409,'This upload has already been removed.')
        ids=db.execute(text('SELECT id FROM commission_documents WHERE franchise_user_id=:fid AND branch_key=:branch AND mf_key=:mf'),{'fid':fid,'branch':row['branch_key'],'mf':row['mf_key']}).scalars().all()
        related=db.execute(text('''SELECT id FROM commission_entries WHERE franchise_user_id=:fid AND status='approved' AND COALESCE(is_cancelled,FALSE)=FALSE
            AND (mortuary_document_id IN :ids OR invoice_document_id IN :ids OR receipt_document_id IN :ids)''').bindparams(bindparam('ids',expanding=True)),{'fid':fid,'ids':ids}).scalars().all()
        if related:
            audit(db,current_user,fid,'commission_document_deletion_blocked',document_id,new={'commission_entry_ids':related},note=payload.reason.strip())
            db.commit()
            raise HTTPException(409,'This case has approved commissions. Head Office must review those entries before a document can be removed.')
        db.execute(text('UPDATE commission_documents SET deleted_at=:now,deleted_by_user_id=:actor,deletion_reason=:reason WHERE id=:id'),{'now':datetime.now(timezone.utc).replace(tzinfo=None),'actor':current_user.id,'reason':payload.reason.strip(),'id':document_id})
        audit(db,current_user,fid,'commission_document_deleted',document_id,old=json.loads(row['source_data']),note=payload.reason.strip())
        db.commit();return {'deleted':True,'message':'Removed from active evidence. The original and audit history are retained.'}
    except Exception: db.rollback();raise


@router.post('/{document_id}/restore')
def restore(document_id: int, payload: CorrectionIn, current_user: User = Depends(get_current_user), db=Depends(get_db)):
    fid=import_scope(db,current_user,payload.franchise_user_id)
    try:
        db.execute(text('SELECT pg_advisory_xact_lock(:namespace,:fid)'),{'namespace':15015,'fid':fid})
        row=document(db,fid,document_id)
        if not row['deleted_at']: raise HTTPException(409,'This document is already active.')
        if len(payload.reason.strip())<3: raise HTTPException(400,'Enter a reason for restoring this upload.')
        conflict=db.execute(text("SELECT id FROM commission_documents WHERE franchise_user_id=:fid AND kind=:kind AND branch_key=:branch AND (document_key=:key OR (:kind IN ('invoice','mortuary') AND mf_key=:mf)) AND deleted_at IS NULL"),{'fid':fid,'kind':row['kind'],'branch':row['branch_key'],'key':row['document_key'],'mf':row['mf_key']}).scalar()
        if conflict: raise HTTPException(409,'A replacement document is active. Remove the incorrect replacement before restoring this one.')
        db.execute(text('UPDATE commission_documents SET deleted_at=NULL,deleted_by_user_id=NULL,deletion_reason=NULL WHERE id=:id'),{'id':document_id})
        audit(db,current_user,fid,'commission_document_restored',document_id,old={'deleted_at':row['deleted_at'],'reason':row['deletion_reason']},note=payload.reason.strip())
        db.commit();return {'restored':True}
    except Exception: db.rollback();raise

