from datetime import date
from decimal import Decimal
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_user_role_names, get_current_franchise_user_id
from app.db.session import get_db
from app.models.core import User

router = APIRouter()

COMMISSION_TYPES = {
    "removals", "grave_service", "full_funeral_service", "cremation_service",
    "church_service", "invoice_commission", "overtime",
}

class StructureIn(BaseModel):
    commission_type: str
    label: str
    calculation_type: str = Field(pattern="^(fixed|percentage|overtime)$")
    rate: Decimal = Field(ge=0)
    overtime_multiplier: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True

class EntryIn(BaseModel):
    employee_user_id: int
    commission_type: str
    service_date: date
    reference: str | None = None
    quantity: Decimal = Field(default=1, gt=0)
    invoice_value_before_tax: Decimal | None = Field(default=None, ge=0)
    hours: Decimal | None = Field(default=None, ge=0)
    hourly_rate: Decimal | None = Field(default=None, ge=0)
    rate_override: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


def _profile(db: Session, user: User):
    roles = get_user_role_names(db, user.id)
    if "FranchiseUser" in roles:
        return roles, get_current_franchise_user_id(db, user), None, None
    if "ManagerUser" in roles:
        row = db.execute(text("SELECT id, franchise_user_id FROM manager_users WHERE user_id=:uid"), {"uid": user.id}).mappings().first()
        return roles, int(row["franchise_user_id"]) if row and row["franchise_user_id"] else None, int(row["id"]) if row else None, None
    if "EmployeeUser" in roles:
        row = db.execute(text("SELECT id, franchise_user_id, manager_user_id FROM employee_users WHERE user_id=:uid"), {"uid": user.id}).mappings().first()
        return roles, int(row["franchise_user_id"]) if row and row["franchise_user_id"] else None, int(row["manager_user_id"]) if row and row["manager_user_id"] else None, int(row["id"]) if row else None
    if "SuperUser" in roles:
        return roles, None, None, None
    raise HTTPException(403, "Commission access is not available for this account")


def _assert_employee_scope(db: Session, user: User, employee_user_id: int, write=False):
    roles, franchise_id, manager_id, own_employee_id = _profile(db, user)
    row = db.execute(text("SELECT id, user_id, franchise_user_id, manager_user_id FROM employee_users WHERE user_id=:uid AND COALESCE(is_active, TRUE)=TRUE"), {"uid": employee_user_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Employee not found")
    if "SuperUser" in roles:
        return row
    if "FranchiseUser" in roles and int(row["franchise_user_id"] or 0) == int(franchise_id or 0):
        return row
    if not write and "ManagerUser" in roles and int(row["manager_user_id"] or 0) == int(manager_id or 0):
        return row
    if not write and "EmployeeUser" in roles and int(row["id"]) == int(own_employee_id or 0):
        return row
    raise HTTPException(403, "Employee is outside your commission scope")


@router.get("/types")
def types():
    return [
        {"value":"removals","label":"Removals"}, {"value":"grave_service","label":"Grave Service"},
        {"value":"full_funeral_service","label":"Full Funeral Service"}, {"value":"cremation_service","label":"Cremation Service"},
        {"value":"church_service","label":"Church Service"}, {"value":"invoice_commission","label":"Invoice Commission"},
        {"value":"overtime","label":"Overtime"},
    ]


@router.get("/employees")
def employees(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles, franchise_id, manager_id, own_employee_id = _profile(db, current_user)
    where, params = ["COALESCE(e.is_active, TRUE)=TRUE"], {}
    if "FranchiseUser" in roles:
        where.append("e.franchise_user_id=:fid"); params["fid"] = franchise_id
    elif "ManagerUser" in roles:
        where.append("e.manager_user_id=:mid"); params["mid"] = manager_id
    elif "EmployeeUser" in roles:
        where.append("e.id=:eid"); params["eid"] = own_employee_id
    rows = db.execute(text(f"""SELECT e.user_id, COALESCE(NULLIF(TRIM(CONCAT(COALESCE(e.name,''),' ',COALESCE(e.surname,''))),''),u.full_name) full_name,
        e.employee_number FROM employee_users e JOIN users u ON u.id=e.user_id WHERE {' AND '.join(where)} ORDER BY full_name"""), params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/structures")
def list_structures(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles, franchise_id, _, _ = _profile(db, current_user)
    if not franchise_id:
        return []
    rows = db.execute(text("SELECT * FROM commission_structures WHERE franchise_user_id=:fid ORDER BY label"), {"fid":franchise_id}).mappings().all()
    return [dict(r) for r in rows]


@router.post("/structures")
def save_structure(payload: StructureIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles, franchise_id, _, _ = _profile(db, current_user)
    if "FranchiseUser" not in roles and "SuperUser" not in roles:
        raise HTTPException(403, "Only a franchise user can manage commission structures")
    if not franchise_id:
        raise HTTPException(400, "Franchise profile required")
    if payload.commission_type not in COMMISSION_TYPES:
        raise HTTPException(400, "Invalid commission type")
    row = db.execute(text("""INSERT INTO commission_structures
      (franchise_user_id, commission_type, label, calculation_type, rate, overtime_multiplier, is_active, created_by_user_id, updated_at)
      VALUES (:fid,:type,:label,:calc,:rate,:mult,:active,:uid,NOW())
      ON CONFLICT (franchise_user_id, commission_type) DO UPDATE SET label=EXCLUDED.label, calculation_type=EXCLUDED.calculation_type,
      rate=EXCLUDED.rate, overtime_multiplier=EXCLUDED.overtime_multiplier, is_active=EXCLUDED.is_active, updated_at=NOW()
      RETURNING *"""), {"fid":franchise_id,"type":payload.commission_type,"label":payload.label,"calc":payload.calculation_type,
        "rate":payload.rate,"mult":payload.overtime_multiplier,"active":payload.is_active,"uid":current_user.id}).mappings().first()
    db.commit(); return dict(row)


@router.post("/entries")
def create_entry(payload: EntryIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles, franchise_id, _, _ = _profile(db, current_user)
    if "FranchiseUser" not in roles and "SuperUser" not in roles:
        raise HTTPException(403, "Only a franchise user can add commission or overtime")
    employee = _assert_employee_scope(db, current_user, payload.employee_user_id, write=True)
    structure = db.execute(text("SELECT * FROM commission_structures WHERE franchise_user_id=:fid AND commission_type=:type AND is_active=TRUE"), {"fid":employee["franchise_user_id"],"type":payload.commission_type}).mappings().first()
    if not structure:
        raise HTTPException(400, "Create an active structure for this commission type first")
    qty = Decimal(payload.quantity)
    if payload.commission_type == "invoice_commission":
        if payload.invoice_value_before_tax is None: raise HTTPException(400, "Invoice value before tax is required")
        rate = Decimal(payload.rate_override if payload.rate_override is not None else structure["rate"])
        amount = Decimal(payload.invoice_value_before_tax) * rate / Decimal("100")
    elif payload.commission_type == "overtime":
        if payload.hours is None or payload.hourly_rate is None: raise HTTPException(400, "Overtime hours and hourly rate are required")
        mult = Decimal(payload.rate_override if payload.rate_override is not None else (structure["overtime_multiplier"] or structure["rate"] or 1))
        rate = mult
        amount = Decimal(payload.hours) * Decimal(payload.hourly_rate) * mult
    else:
        rate = Decimal(payload.rate_override if payload.rate_override is not None else structure["rate"])
        amount = qty * rate
    row = db.execute(text("""INSERT INTO commission_entries
      (franchise_user_id, employee_user_id, commission_type, service_date, reference, quantity, invoice_value_before_tax,
       hours, hourly_rate, applied_rate, calculated_amount, notes, created_by_user_id)
      VALUES (:fid,:employee,:type,:date,:ref,:qty,:invoice,:hours,:hourly,:rate,:amount,:notes,:uid) RETURNING *"""),
      {"fid":employee["franchise_user_id"],"employee":payload.employee_user_id,"type":payload.commission_type,"date":payload.service_date,
       "ref":payload.reference,"qty":qty,"invoice":payload.invoice_value_before_tax,"hours":payload.hours,"hourly":payload.hourly_rate,
       "rate":rate,"amount":amount.quantize(Decimal("0.01")),"notes":payload.notes,"uid":current_user.id}).mappings().first()
    db.commit(); return dict(row)


def _entry_rows(db, current_user, employee_user_id=None, from_date=None, to_date=None):
    roles, franchise_id, manager_id, own_employee_id = _profile(db, current_user)
    where, params = ["1=1"], {}
    if employee_user_id:
        _assert_employee_scope(db, current_user, employee_user_id, write=False)
        where.append("c.employee_user_id=:employee"); params["employee"] = employee_user_id
    elif "FranchiseUser" in roles:
        where.append("c.franchise_user_id=:fid"); params["fid"] = franchise_id
    elif "ManagerUser" in roles:
        where.append("e.manager_user_id=:mid"); params["mid"] = manager_id
    elif "EmployeeUser" in roles:
        where.append("e.id=:eid"); params["eid"] = own_employee_id
    if from_date: where.append("c.service_date>=:from_date"); params["from_date"] = from_date
    if to_date: where.append("c.service_date<=:to_date"); params["to_date"] = to_date
    return db.execute(text(f"""SELECT c.*, u.full_name employee_name, e.employee_number
      FROM commission_entries c JOIN users u ON u.id=c.employee_user_id JOIN employee_users e ON e.user_id=c.employee_user_id
      WHERE {' AND '.join(where)} ORDER BY c.service_date DESC, c.id DESC"""), params).mappings().all()


@router.get("/entries")
def entries(employee_user_id: int | None = None, from_date: date | None = None, to_date: date | None = None,
            current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = _entry_rows(db,current_user,employee_user_id,from_date,to_date)
    total = sum((Decimal(r["calculated_amount"] or 0) for r in rows), Decimal("0"))
    overtime = sum((Decimal(r["calculated_amount"] or 0) for r in rows if r["commission_type"]=="overtime"), Decimal("0"))
    return {"items":[dict(r) for r in rows],"total":total,"overtime_total":overtime,"commission_total":total-overtime}


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles, franchise_id, _, _ = _profile(db,current_user)
    if "FranchiseUser" not in roles and "SuperUser" not in roles: raise HTTPException(403,"Only a franchise user can delete entries")
    row=db.execute(text("SELECT employee_user_id, franchise_user_id FROM commission_entries WHERE id=:id"),{"id":entry_id}).mappings().first()
    if not row: raise HTTPException(404,"Entry not found")
    _assert_employee_scope(db,current_user,int(row["employee_user_id"]),write=True)
    db.execute(text("DELETE FROM commission_entries WHERE id=:id"),{"id":entry_id}); db.commit(); return {"ok":True}


@router.get("/report.pdf")
def report_pdf(employee_user_id: int | None = Query(default=None), from_date: date | None = None, to_date: date | None = None,
               current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows=_entry_rows(db,current_user,employee_user_id,from_date,to_date)
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    buf=BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=12*mm)
    styles=getSampleStyleSheet(); story=[Paragraph("Employee Commission & Overtime Report",styles["Title"]),Spacer(1,6*mm)]
    data=[["Date","Employee","Type","Reference","Details","Amount"]]
    total=Decimal("0")
    for r in rows:
        amount=Decimal(r["calculated_amount"] or 0); total+=amount
        details=(f"{r['hours']} hrs x R{r['hourly_rate']} x {r['applied_rate']}" if r["commission_type"]=="overtime" else
                 f"Invoice R{r['invoice_value_before_tax']} @ {r['applied_rate']}%" if r["commission_type"]=="invoice_commission" else f"Qty {r['quantity']} @ R{r['applied_rate']}")
        data.append([str(r["service_date"]),r["employee_name"],r["commission_type"].replace("_"," ").title(),r["reference"] or "",details,f"R {amount:,.2f}"])
    data.append(["","","","","TOTAL",f"R {total:,.2f}"])
    table=Table(data,colWidths=[22*mm,38*mm,34*mm,28*mm,45*mm,25*mm],repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eeeeee")),("GRID",(0,0),(-1,-1),0.4,colors.grey),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTNAME",(4,-1),(-1,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),
        ("VALIGN",(0,0),(-1,-1),"TOP"),("ALIGN",(-1,1),(-1,-1),"RIGHT")]))
    story.append(table); doc.build(story); buf.seek(0)
    return StreamingResponse(buf,media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=commission-overtime-report.pdf"})
