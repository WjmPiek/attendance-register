from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_user_role_names, get_current_franchise_user_id
from app.db.session import get_db
from app.models.core import User

router = APIRouter()
COMMISSION_TYPES = {"removals","grave_service","full_funeral_service","cremation_service","church_service","invoice_commission","overtime"}

class StructureIn(BaseModel):
    commission_type: str
    label: str
    calculation_type: str = Field(pattern="^(fixed|percentage|overtime)$")
    rate: Decimal = Field(ge=0)
    overtime_multiplier: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True

class EntryIn(BaseModel):
    employee_user_id: int | None = None
    commission_type: str
    service_date: date
    reference: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(default=1, gt=0)
    invoice_value_before_tax: Decimal | None = Field(default=None, ge=0)
    hours: Decimal | None = Field(default=None, ge=0)
    hourly_rate: Decimal | None = Field(default=None, ge=0)
    rate_override: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None

class ReviewIn(EntryIn):
    status: str = Field(pattern="^(approved|rejected)$")
    review_notes: str | None = None

class BulkReviewIn(BaseModel):
    entry_ids: list[int]
    status: str = Field(pattern="^(approved|rejected)$")
    review_notes: str | None = None


def _profile(db: Session, user: User):
    roles = get_user_role_names(db, user.id)
    if "FranchiseUser" in roles:
        return roles, get_current_franchise_user_id(db, user), None, None
    if "ManagerUser" in roles:
        row=db.execute(text("SELECT id, franchise_user_id FROM manager_users WHERE user_id=:uid"),{"uid":user.id}).mappings().first()
        return roles, int(row["franchise_user_id"]) if row and row["franchise_user_id"] else None, int(row["id"]) if row else None, None
    if "EmployeeUser" in roles:
        row=db.execute(text("SELECT id, franchise_user_id, manager_user_id FROM employee_users WHERE user_id=:uid"),{"uid":user.id}).mappings().first()
        return roles, int(row["franchise_user_id"]) if row and row["franchise_user_id"] else None, int(row["manager_user_id"]) if row and row["manager_user_id"] else None, int(row["id"]) if row else None
    if "SuperUser" in roles: return roles,None,None,None
    raise HTTPException(403,"Commission access is not available for this account")


def _employee(db,user,employee_user_id,write=False):
    roles,fid,mid,eid=_profile(db,user)
    row=db.execute(text("SELECT id,user_id,franchise_user_id,manager_user_id FROM employee_users WHERE user_id=:uid AND COALESCE(is_active,TRUE)=TRUE"),{"uid":employee_user_id}).mappings().first()
    if not row: raise HTTPException(404,"Employee not found")
    if "SuperUser" in roles: return row
    if "FranchiseUser" in roles and int(row["franchise_user_id"] or 0)==int(fid or 0): return row
    if "ManagerUser" in roles and int(row["manager_user_id"] or 0)==int(mid or 0): return row
    if not write and "EmployeeUser" in roles and int(row["id"])==int(eid or 0): return row
    raise HTTPException(403,"Employee is outside your commission scope")


def _calculate(structure,p):
    qty=Decimal(p.quantity)
    if p.commission_type=="invoice_commission":
        if p.invoice_value_before_tax is None: raise HTTPException(400,"Invoice value before tax is required")
        rate=Decimal(p.rate_override if p.rate_override is not None else structure["rate"])
        amount=Decimal(p.invoice_value_before_tax)*rate/Decimal("100")
    elif p.commission_type=="overtime":
        if p.hours is None or p.hourly_rate is None: raise HTTPException(400,"Overtime hours and hourly rate are required")
        rate=Decimal(p.rate_override if p.rate_override is not None else (structure["overtime_multiplier"] or structure["rate"] or 1))
        amount=Decimal(p.hours)*Decimal(p.hourly_rate)*rate
    else:
        rate=Decimal(p.rate_override if p.rate_override is not None else structure["rate"]); amount=qty*rate
    return rate,amount.quantize(Decimal("0.01"))


def _notify(db,user_id,subject,message,entry_id,severity="info"):
    db.execute(text("""INSERT INTO notifications(user_id,recipient_user_id,notification_type,subject,message,status,is_read,severity,target_tab,related_table,related_id,created_at)
      VALUES(:uid,:uid,'commission',:subject,:message,'pending',FALSE,:severity,'commission','commission_entries',:entry,NOW())"""),
      {"uid":user_id,"subject":subject,"message":message,"severity":severity,"entry":entry_id})


def _reviewer_ids(db,employee):
    ids=[]
    f=db.execute(text("SELECT user_id FROM franchise_users WHERE id=:id"),{"id":employee["franchise_user_id"]}).scalar()
    if f: ids.append(int(f))
    if employee["manager_user_id"]:
        m=db.execute(text("SELECT user_id FROM manager_users WHERE id=:id"),{"id":employee["manager_user_id"]}).scalar()
        if m: ids.append(int(m))
    return list(dict.fromkeys(ids))


def _audit(db,entry_id,action,actor,old=None,new=None,note=None):
    db.execute(text("INSERT INTO commission_entry_audit(entry_id,action,actor_user_id,old_values,new_values,note) VALUES(:e,:a,:u,:o,:n,:note)"),
      {"e":entry_id,"a":action,"u":actor,"o":json.dumps(old,default=str) if old else None,"n":json.dumps(new,default=str) if new else None,"note":note})

@router.get('/types')
def types():
    return [{"value":x,"label":x.replace('_',' ').title()} for x in sorted(COMMISSION_TYPES)]

@router.get('/employees')
def employees(current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    roles,fid,mid,eid=_profile(db,current_user); where=["COALESCE(e.is_active,TRUE)=TRUE"]; p={}
    if "FranchiseUser" in roles: where.append("e.franchise_user_id=:fid");p["fid"]=fid
    elif "ManagerUser" in roles: where.append("e.manager_user_id=:mid");p["mid"]=mid
    elif "EmployeeUser" in roles: where.append("e.id=:eid");p["eid"]=eid
    rows=db.execute(text(f"SELECT e.user_id,COALESCE(NULLIF(TRIM(CONCAT(COALESCE(e.name,''),' ',COALESCE(e.surname,''))),''),u.full_name) full_name,e.employee_number FROM employee_users e JOIN users u ON u.id=e.user_id WHERE {' AND '.join(where)} ORDER BY full_name"),p).mappings().all()
    return [dict(r) for r in rows]

@router.get('/structures')
def structures(current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    _,fid,_,_=_profile(db,current_user)
    if not fid:return []
    return [dict(r) for r in db.execute(text("SELECT * FROM commission_structures WHERE franchise_user_id=:fid ORDER BY label"),{"fid":fid}).mappings().all()]

@router.post('/structures')
def save_structure(payload:StructureIn,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    roles,fid,_,_=_profile(db,current_user)
    if "FranchiseUser" not in roles and "SuperUser" not in roles: raise HTTPException(403,"Only a franchise user can manage commission structures")
    if not fid: raise HTTPException(400,"Franchise profile required")
    row=db.execute(text("""INSERT INTO commission_structures(franchise_user_id,commission_type,label,calculation_type,rate,overtime_multiplier,is_active,created_by_user_id,updated_at)
      VALUES(:fid,:type,:label,:calc,:rate,:mult,:active,:uid,NOW()) ON CONFLICT(franchise_user_id,commission_type) DO UPDATE SET label=EXCLUDED.label,calculation_type=EXCLUDED.calculation_type,rate=EXCLUDED.rate,overtime_multiplier=EXCLUDED.overtime_multiplier,is_active=EXCLUDED.is_active,updated_at=NOW() RETURNING *"""),
      {"fid":fid,"type":payload.commission_type,"label":payload.label,"calc":payload.calculation_type,"rate":payload.rate,"mult":payload.overtime_multiplier,"active":payload.is_active,"uid":current_user.id}).mappings().first();db.commit();return dict(row)

@router.post('/entries')
def create_entry(payload:EntryIn,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    roles,_,_,own_eid=_profile(db,current_user)
    if "EmployeeUser" in roles:
        employee_user_id=current_user.id; status="pending"
    elif "FranchiseUser" in roles or "SuperUser" in roles:
        if not payload.employee_user_id: raise HTTPException(400,"Employee is required")
        employee_user_id=payload.employee_user_id; status="approved"
    else: raise HTTPException(403,"Employees may submit and franchise users may add entries")
    employee=_employee(db,current_user,employee_user_id,write="EmployeeUser" not in roles)
    structure=db.execute(text("SELECT * FROM commission_structures WHERE franchise_user_id=:fid AND commission_type=:type AND is_active=TRUE"),{"fid":employee["franchise_user_id"],"type":payload.commission_type}).mappings().first()
    if not structure: raise HTTPException(400,"This commission type is not active")
    rate,amount=_calculate(structure,payload)
    row=db.execute(text("""INSERT INTO commission_entries(franchise_user_id,employee_user_id,commission_type,service_date,reference,quantity,invoice_value_before_tax,hours,hourly_rate,applied_rate,calculated_amount,notes,created_by_user_id,status,submitted_at,reviewed_at,reviewed_by_user_id,last_edited_by_user_id)
      VALUES(:fid,:employee,:type,:date,:ref,:qty,:invoice,:hours,:hourly,:rate,:amount,:notes,:uid,:status,NOW(),CASE WHEN :status='approved' THEN NOW() ELSE NULL END,CASE WHEN :status='approved' THEN :uid ELSE NULL END,:uid) RETURNING *"""),
      {"fid":employee["franchise_user_id"],"employee":employee_user_id,"type":payload.commission_type,"date":payload.service_date,"ref":payload.reference.strip(),"qty":payload.quantity,"invoice":payload.invoice_value_before_tax,"hours":payload.hours,"hourly":payload.hourly_rate,"rate":rate,"amount":amount,"notes":payload.notes,"uid":current_user.id,"status":status}).mappings().first()
    _audit(db,row["id"],"submitted" if status=="pending" else "created_approved",current_user.id,new=dict(row))
    if status=="pending":
        name=db.execute(text("SELECT full_name FROM users WHERE id=:id"),{"id":current_user.id}).scalar() or "Employee"
        for uid in _reviewer_ids(db,employee): _notify(db,uid,"New commission submitted",f"{name} submitted {structure['label']} reference {payload.reference}. Click to review and edit.",row["id"],"warning")
    db.commit();return dict(row)


def _rows(db,user,employee_user_id=None,from_date=None,to_date=None,status=None,search=None):
    roles,fid,mid,eid=_profile(db,user); where=["1=1"];p={}
    if employee_user_id: _employee(db,user,employee_user_id);where.append("c.employee_user_id=:employee");p["employee"]=employee_user_id
    elif "FranchiseUser" in roles:where.append("c.franchise_user_id=:fid");p["fid"]=fid
    elif "ManagerUser" in roles:where.append("e.manager_user_id=:mid");p["mid"]=mid
    elif "EmployeeUser" in roles:where.append("e.id=:eid");p["eid"]=eid
    if from_date:where.append("c.service_date>=:fd");p["fd"]=from_date
    if to_date:where.append("c.service_date<=:td");p["td"]=to_date
    if status:where.append("c.status=:status");p["status"]=status
    if search:where.append("(LOWER(COALESCE(c.reference,'')) LIKE :q OR LOWER(u.full_name) LIKE :q OR LOWER(c.commission_type) LIKE :q)");p["q"]=f"%{search.lower()}%"
    return db.execute(text(f"""SELECT c.*,u.full_name employee_name,e.employee_number,rv.full_name reviewer_name
      FROM commission_entries c JOIN users u ON u.id=c.employee_user_id JOIN employee_users e ON e.user_id=c.employee_user_id LEFT JOIN users rv ON rv.id=c.reviewed_by_user_id
      WHERE {' AND '.join(where)} ORDER BY CASE WHEN c.status='pending' THEN 0 ELSE 1 END,c.service_date DESC,c.id DESC"""),p).mappings().all()

@router.get('/entries')
def entries(employee_user_id:int|None=None,from_date:date|None=None,to_date:date|None=None,status:str|None=None,search:str|None=None,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    rows=_rows(db,current_user,employee_user_id,from_date,to_date,status,search); approved=[r for r in rows if r["status"]=="approved"]
    total=sum((Decimal(r["calculated_amount"] or 0) for r in approved),Decimal(0)); overtime=sum((Decimal(r["calculated_amount"] or 0) for r in approved if r["commission_type"]=="overtime"),Decimal(0))
    counts={x:sum(1 for r in rows if r["status"]==x) for x in ["pending","approved","rejected"]}
    return {"items":[dict(r) for r in rows],"total":total,"commission_total":total-overtime,"overtime_total":overtime,"counts":counts}

@router.get('/entries/{entry_id}')
def get_entry(entry_id:int,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    row=db.execute(text("SELECT * FROM commission_entries WHERE id=:id"),{"id":entry_id}).mappings().first()
    if not row:raise HTTPException(404,"Entry not found")
    _employee(db,current_user,int(row["employee_user_id"]));return dict(row)

@router.put('/entries/{entry_id}/review')
def review(entry_id:int,payload:ReviewIn,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    roles,_,_,_=_profile(db,current_user)
    if not ({"FranchiseUser","ManagerUser","SuperUser"}&roles):raise HTTPException(403,"Review access required")
    old=db.execute(text("SELECT * FROM commission_entries WHERE id=:id"),{"id":entry_id}).mappings().first()
    if not old:raise HTTPException(404,"Entry not found")
    employee=_employee(db,current_user,int(old["employee_user_id"]),write=True)
    structure=db.execute(text("SELECT * FROM commission_structures WHERE franchise_user_id=:fid AND commission_type=:type AND is_active=TRUE"),{"fid":employee["franchise_user_id"],"type":payload.commission_type}).mappings().first()
    if not structure:raise HTTPException(400,"This commission type is not active")
    rate,amount=_calculate(structure,payload)
    row=db.execute(text("""UPDATE commission_entries SET commission_type=:type,service_date=:date,reference=:ref,quantity=:qty,invoice_value_before_tax=:invoice,hours=:hours,hourly_rate=:hourly,applied_rate=:rate,calculated_amount=:amount,notes=:notes,status=:status,review_notes=:review_notes,reviewed_at=NOW(),reviewed_by_user_id=:uid,last_edited_by_user_id=:uid,updated_at=NOW() WHERE id=:id RETURNING *"""),
      {"type":payload.commission_type,"date":payload.service_date,"ref":payload.reference.strip(),"qty":payload.quantity,"invoice":payload.invoice_value_before_tax,"hours":payload.hours,"hourly":payload.hourly_rate,"rate":rate,"amount":amount,"notes":payload.notes,"status":payload.status,"review_notes":payload.review_notes,"uid":current_user.id,"id":entry_id}).mappings().first()
    _audit(db,entry_id,payload.status,current_user.id,dict(old),dict(row),payload.review_notes)
    edited=any(str(old.get(k))!=str(row.get(k)) for k in ["commission_type","service_date","reference","quantity","invoice_value_before_tax","hours","hourly_rate","calculated_amount","notes"])
    subject="Commission review form approved" if payload.status=="approved" else "Commission review form rejected"
    msg=f"Your commission reference {row['reference']} was {payload.status}."+(" Details were updated during review." if edited else "")+(f" Note: {payload.review_notes}" if payload.review_notes else "")
    _notify(db,int(row["employee_user_id"]),subject,msg,entry_id,"success" if payload.status=="approved" else "danger")
    db.commit();return dict(row)

@router.post('/entries/bulk-review')
def bulk_review(payload:BulkReviewIn,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    done=[]
    for eid in payload.entry_ids:
        row=db.execute(text("SELECT * FROM commission_entries WHERE id=:id"),{"id":eid}).mappings().first()
        if not row:continue
        _employee(db,current_user,int(row["employee_user_id"]),write=True)
        db.execute(text("UPDATE commission_entries SET status=:s,review_notes=:n,reviewed_at=NOW(),reviewed_by_user_id=:u,last_edited_by_user_id=:u,updated_at=NOW() WHERE id=:id"),{"s":payload.status,"n":payload.review_notes,"u":current_user.id,"id":eid})
        _audit(db,eid,f"bulk_{payload.status}",current_user.id,note=payload.review_notes)
        _notify(db,int(row["employee_user_id"]),"Commission review form approved" if payload.status=="approved" else "Commission review form rejected",f"Your commission reference {row['reference']} was {payload.status}.",eid,"success" if payload.status=="approved" else "danger");done.append(eid)
    db.commit();return {"updated":done}

@router.delete('/entries/{entry_id}')
def delete_entry(entry_id:int,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    roles,_,_,_=_profile(db,current_user)
    if "FranchiseUser" not in roles and "SuperUser" not in roles:raise HTTPException(403,"Only a franchise user can delete entries")
    row=db.execute(text("SELECT employee_user_id FROM commission_entries WHERE id=:id"),{"id":entry_id}).mappings().first()
    if not row:raise HTTPException(404,"Entry not found")
    _employee(db,current_user,int(row["employee_user_id"]),write=True);db.execute(text("DELETE FROM commission_entries WHERE id=:id"),{"id":entry_id});db.commit();return {"ok":True}


def _pdf(rows,title):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image
    buf=BytesIO();styles=getSampleStyleSheet();doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=14*mm)
    logo=Path(__file__).resolve().parents[1]/'static'/'logo.png'; company=Paragraph('<b>Attendance Register Platform</b><br/>Commission Administration',styles['Normal'])
    logo_flow=Image(str(logo),width=48*mm,height=18*mm,kind='proportional') if logo.exists() else Paragraph('<b>COMPANY LOGO</b>',styles['Heading2'])
    header=Table([[company,logo_flow]],colWidths=[120*mm,60*mm]);header.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LINEBELOW',(0,0),(-1,-1),1,colors.HexColor('#333333'))]))
    story=[header,Spacer(1,5*mm),Paragraph(title,styles['Title']),Paragraph(f"Generated: {datetime.now().strftime('%d %B %Y %H:%M')}",styles['Normal']),Spacer(1,4*mm)]
    data=[["Date","Employee","Type","Reference","Status","Details","Amount"]];total=Decimal(0)
    for r in rows:
        amount=Decimal(r['calculated_amount'] or 0)
        if r['status']=='approved':total+=amount
        details=f"{r['hours']} hrs x R{r['hourly_rate']} x {r['applied_rate']}" if r['commission_type']=='overtime' else (f"Invoice R{r['invoice_value_before_tax']} @ {r['applied_rate']}%" if r['commission_type']=='invoice_commission' else f"Qty {r['quantity']} @ R{r['applied_rate']}")
        data.append([str(r['service_date']),r.get('employee_name',''),r['commission_type'].replace('_',' ').title(),r['reference'] or '',r['status'].title(),details,f"R {amount:,.2f}"])
    data.append(["","","","","","APPROVED TOTAL",f"R {total:,.2f}"])
    table=Table(data,colWidths=[20*mm,31*mm,28*mm,27*mm,20*mm,42*mm,22*mm],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8edf3')),('GRID',(0,0),(-1,-1),.35,colors.grey),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(-2,-1),(-1,-1),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(-1,1),(-1,-1),'RIGHT')]))
    story.extend([table,Spacer(1,8*mm),Paragraph('Authorisation',styles['Heading3']),Paragraph('Approved by: ______________________________    Date: ____________________',styles['Normal'])]);doc.build(story);buf.seek(0);return buf

@router.get('/report.pdf')
def report_pdf(employee_user_id:int|None=Query(default=None),from_date:date|None=None,to_date:date|None=None,status:str|None=None,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    return StreamingResponse(_pdf(_rows(db,current_user,employee_user_id,from_date,to_date,status),"Employee Commission & Overtime Report"),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename=commission-overtime-report.pdf'})

@router.get('/entries/{entry_id}/form.pdf')
def form_pdf(entry_id:int,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    rows=_rows(db,current_user); selected=[r for r in rows if int(r['id'])==entry_id]
    if not selected:raise HTTPException(404,"Entry not found")
    return StreamingResponse(_pdf(selected,"Commission Review Form"),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename=commission-form-{entry_id}.pdf'})
