from datetime import date, datetime
from io import BytesIO
import json
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api import requisitions as api
from app.api.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.models.core import (
    User,
    Role,
    UserRole,
    FranchiseUser,
    EmployeeUser,
    ManagerUser,
)
from app.models.requisitions import RequisitionEmail, Requisition, RequisitionMonth
from app.services import requisitions as service


@pytest.fixture
def system(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.execute(
            text(
                "CREATE TABLE attendance_branches(id INTEGER PRIMARY KEY,franchise_user_id INTEGER,name TEXT,is_active BOOLEAN)"
            )
        )
        db.execute(text("CREATE TABLE external_commission_branches(branch_id INTEGER)"))
        for uid, role in [
            (1, "FranchiseUser"),
            (2, "EmployeeUser"),
            (3, "ManagerUser"),
            (4, "FranchiseUser"),
            (5, "SuperUser"),
        ]:
            if not db.scalar(select(Role).where(Role.name == role)):
                db.add(Role(name=role))
                db.flush()
            db.add(
                User(
                    id=uid,
                    full_name=f"User {uid}",
                    email=f"user{uid}@example.test",
                    password_hash="unused",
                    is_active=True,
                )
            )
            db.flush()
            db.add(
                UserRole(
                    user_id=uid,
                    role_id=db.scalar(select(Role.id).where(Role.name == role)),
                )
            )
        db.add_all(
            [
                FranchiseUser(id=10, user_id=1, franchise_name="Linked branches"),
                FranchiseUser(id=20, user_id=4, franchise_name="Other holder"),
            ]
        )
        db.flush()
        db.add(EmployeeUser(user_id=2, franchise_user_id=10))
        db.add(ManagerUser(user_id=3, franchise_user_id=10))
        for bid, fid, name in [
            (101, 10, "Northcliff"),
            (102, 10, "Rivonia"),
            (103, 10, "Benoni"),
            (201, 20, "Outside"),
        ]:
            db.execute(
                text("INSERT INTO attendance_branches VALUES(:bid,:fid,:name,TRUE)"),
                {"bid": bid, "fid": fid, "name": name},
            )
        db.commit()
    actor = [1]

    def database():
        with Session(engine) as db:
            yield db

    def user():
        with Session(engine) as db:
            return db.get(User, actor[0])

    app = FastAPI()
    app.include_router(api.router, prefix="/api/requisitions")
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = user
    monkeypatch.setattr(service, "deliver_pending", lambda: None)
    with TestClient(app) as client:
        yield client, engine, actor


def book_pdf(branch="Northcliff", reference="MF123"):
    out = BytesIO()
    pdf = canvas.Canvas(out, invariant=1)
    content = f"""MORTUARY BOOK REGISTER DETAILS
Branch Name {branch} Date Generated 02 Nov 2026
MF Number {reference} Body Number N/A
Name and Surname of Deceased Example Person
ID Number 0000000000000 Age 85 Sex MALE
Driver Example
Collected At Example location
Driver In Example
Date In 01 Nov 2026 Time In 10h00"""
    for i, line in enumerate(content.splitlines()):
        pdf.drawString(25, 800 - i * 20, line)
    pdf.save()
    return out.getvalue()


def create_case(client):
    r = client.post(
        "/api/requisitions/months",
        json={
            "branch_id": 101,
            "month": "2026-11",
            "holder": "Test holder",
            "opening_balance": "500.00",
        },
    )
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    r = client.post(
        "/api/requisitions/books/import?branch_id=101",
        files={"file": ("book.pdf", book_pdf(), "application/pdf")},
    )
    assert r.status_code == 200, r.text
    bid = r.json()["items"][0]["id"]
    r = client.post(
        "/api/requisitions/requests",
        json={"month_id": mid, "book_id": bid, "request_date": "2026-11-02"},
    )
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    r = client.put(
        f"/api/requisitions/requests/{rid}",
        json={
            "details": {"funeral_date": "2026-11-04"},
            "lines": [
                {
                    "description": "Cremation (EFT)",
                    "method": "eft",
                    "amount": "2000.00",
                },
                {"description": "Fuel", "method": "card", "amount": "600.35"},
                {"description": "Printer", "method": "card", "amount": "150.00"},
                {"description": "Cash service", "method": "cash", "amount": "499.65"},
            ],
        },
    )
    assert r.status_code == 200, r.text
    return mid, rid, bid


def transaction(client, rid, kind, amount, day="2026-11-02", key=None):
    return client.post(
        "/api/requisitions/transactions",
        data={
            "payload": json.dumps(
                {
                    "requisition_id": rid,
                    "client_key": key or str(uuid4()),
                    "transaction_date": day,
                    "kind": kind,
                    "supplier": "Supplier",
                    "description": "Service",
                    "amount": amount,
                }
            )
        },
        files={"receipt": ("proof.pdf", book_pdf(), "application/pdf")},
    )


def test_selected_staff_linked_branches_and_tenant_isolation(system):
    client, engine, actor = system
    actor[0] = 2
    assert client.get("/api/requisitions/access").json()["enabled"] is False
    assert client.get("/api/requisitions/months?branch_id=101").status_code == 403
    actor[0] = 1
    assert (
        client.put(
            "/api/requisitions/grants", json={"user_id": 2, "enabled": True}
        ).status_code
        == 200
    )
    actor[0] = 2
    access = client.get("/api/requisitions/access").json()
    assert {b["id"] for b in access["branches"]} == {101, 102, 103}
    assert client.get("/api/requisitions/months?branch_id=201").status_code == 403
    assert (
        client.get(
            "/api/requisitions/months?branch_id=101&franchise_user_id=20"
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/api/requisitions/grants", json={"user_id": 3, "enabled": True}
        ).status_code
        == 403
    )
    actor[0] = 1
    client.put("/api/requisitions/grants", json={"user_id": 2, "enabled": False})
    actor[0] = 2
    assert client.get("/api/requisitions/books?branch_id=101").status_code == 403
    actor[0] = 3
    assert client.get("/api/requisitions/access").json()["enabled"] is False
    actor[0] = 5
    assert client.get("/api/requisitions/access").json()["holders"]
    assert client.get("/api/requisitions/books?branch_id=101").status_code == 400


def test_submit_totals_exact_cents_and_email_snapshot(system):
    client, engine, actor = system
    mid, rid, bid = create_case(client)
    r = client.post(f"/api/requisitions/requests/{rid}/submit")
    assert r.status_code == 200, r.text
    assert r.json()["total_cents"] == 325000
    assert r.json()["number"]
    assert client.post(f"/api/requisitions/requests/{rid}/submit").status_code == 200
    assert (
        client.put(
            f"/api/requisitions/requests/{rid}", json={"details": {}, "lines": []}
        ).status_code
        == 400
    )
    assert (
        client.get(f"/api/requisitions/months/{mid}").json()["balance_cents"] == 50000
    )
    with Session(engine) as db:
        messages = db.scalars(select(RequisitionEmail)).all()
        assert len(messages) == 1
        assert messages[0].document.startswith(b"%PDF-")
        assert messages[0].workbook.startswith(b"PK")
        wb = load_workbook(BytesIO(messages[0].workbook))
        assert wb.sheetnames == [
            "KAART TRANSAKSIES",
            "Rekwisisie Vorm - 1",
            "Instruksies",
        ]
        assert wb.worksheets[0]["K10"].value == 500
        assert wb.worksheets[0]["G86"].value == 750.35
        assert wb.worksheets[1]["B11"].value == "MF123"
        assert wb.worksheets[1]["B14"].value == "Example Person"
        assert wb.worksheets[1]["D35"].value == "=SUM(D28:D34)"
        assert wb.worksheets[1]["C10"].value == r.json()["number"]
    actor[0] = 4
    for path in [
        f"/requests/{rid}",
        f"/requests/{rid}/pdf",
        f"/books/{bid}/file",
        f"/months/{mid}/workbook",
    ]:
        assert client.get("/api/requisitions" + path).status_code == 404


def test_card_cash_eft_receipts_idempotency_and_month_rollover(system):
    client, engine, actor = system
    mid, rid, _ = create_case(client)
    client.post(f"/api/requisitions/requests/{rid}/submit")
    key = str(uuid4())
    r = transaction(client, rid, "funding", "3250.00", key=key)
    assert r.status_code == 200, r.text
    assert transaction(client, rid, "funding", "3250.00", key=key).json()["duplicate"]
    assert transaction(client, rid, "funding", "3251.00", key=key).status_code == 409
    for kind, amount in [
        ("card", "600.35"),
        ("card", "150.00"),
        ("eft", "2000.00"),
        ("cash", "499.65"),
    ]:
        r = transaction(client, rid, kind, amount)
        assert r.status_code == 200, r.text
    ledger = client.get(f"/api/requisitions/months/{mid}").json()
    assert ledger["balance_cents"] == 99965
    assert len(ledger["transactions"]) == 5
    receipt = ledger["transactions"][0]["id"]
    assert client.get(
        f"/api/requisitions/transactions/{receipt}/receipt"
    ).content.startswith(b"%PDF-")
    wb = load_workbook(
        BytesIO(client.get(f"/api/requisitions/months/{mid}/workbook").content)
    )
    assert wb.active["K11"].value == "=K10+G11-I11-J11"
    for row in (59, 69, 81):
        assert wb.active[f"K{row}"].value == f"=K{row-1}+G{row}-I{row}-J{row}"
    assert client.post(f"/api/requisitions/months/{mid}/close").status_code == 200
    assert transaction(client, rid, "card", "1.00").status_code == 409
    r = client.post(
        "/api/requisitions/months",
        json={
            "branch_id": 101,
            "month": "2026-12",
            "holder": "Next holder",
            "opening_balance": "999",
        },
    )
    assert r.status_code == 200, r.text
    new_mid = r.json()["id"]
    assert (
        client.get(f"/api/requisitions/months/{new_mid}").json()["opening_cents"]
        == 99965
    )
    assert (
        transaction(client, rid, "card", "49.65", day="2026-12-01").status_code == 200
    )
    # A later receipt retains the original November requisition number.
    later = client.get(f"/api/requisitions/months/{new_mid}").json()
    assert later["balance_cents"] == 95000
    assert later["transactions"][0]["number"]
    assert (
        client.get(f"/api/requisitions/months/{mid}").json()["balance_cents"] == 99965
    )
    actor[0] = 4
    assert (
        client.get(f"/api/requisitions/transactions/{receipt}/receipt").status_code
        == 404
    )


def test_authority_validation_import_atomicity_and_funding_permissions(system):
    client, engine, actor = system
    mid, rid, _ = create_case(client)
    bad = client.post(
        "/api/requisitions/books/import?branch_id=101",
        files={"file": ("wrong.pdf", book_pdf("Rivonia"), "application/pdf")},
    )
    assert bad.status_code == 400
    assert len(client.get("/api/requisitions/books?branch_id=101").json()) == 1
    assert client.post(f"/api/requisitions/months/{mid}/close").status_code == 409
    assert transaction(client, rid, "card", "1.00").status_code == 409
    assert (
        client.put(
            f"/api/requisitions/requests/{rid}",
            json={
                "details": {},
                "lines": [
                    {"description": "Bad cents", "method": "card", "amount": "0.001"}
                ],
            },
        ).status_code
        == 422
    )
    client.post(f"/api/requisitions/requests/{rid}/submit")
    client.put("/api/requisitions/grants", json={"user_id": 2, "enabled": True})
    actor[0] = 2
    assert transaction(client, rid, "funding", "10.00").status_code == 403
    assert transaction(client, rid, "eft", "10.00").status_code == 403
    assert transaction(client, rid, "card", "10.00").status_code == 200
    assert (
        client.post(
            "/api/requisitions/months",
            json={"branch_id": 101, "month": "2026-12", "holder": "No"},
        ).status_code
        == 403
    )


def test_blank_export_and_untrusted_excel_text(system):
    client, engine, actor = system
    mid, rid, _ = create_case(client)
    client.put(
        f"/api/requisitions/requests/{rid}",
        json={
            "details": {"venue": '=HYPERLINK("evil")'},
            "lines": [{"description": "=SUM(1,2)", "method": "card", "amount": "2.10"}],
        },
    )
    client.post(f"/api/requisitions/requests/{rid}/submit")
    wb = load_workbook(
        BytesIO(client.get(f"/api/requisitions/months/{mid}/workbook").content)
    )
    form = wb["Rekwisisie Vorm - 1"]
    assert all(c.data_type != "f" for row in form for c in row if c.column != 4)
    blank = load_workbook(
        BytesIO(
            client.get(f"/api/requisitions/months/{mid}/workbook?blank=true").content
        )
    )
    assert blank.active["K10"].value == 0
    assert blank.sheetnames == [
        "KAART TRANSAKSIES",
        "Rekwisisie Vorm - 1",
        "Rekwisisie Vorm - 2",
        "Rekwisisie Vorm - 3",
        "Instruksies",
    ]
    assert blank["Rekwisisie Vorm - 1"]["D10"].value is None


def test_template_fields_logos_and_expanding_payment_and_ledger_rows(system):
    client, engine, actor = system
    mid, rid, _ = create_case(client)
    details = {
        "id_number": "0000000000000",
        "date_of_death": "2026-11-01",
        "funeral_date": "2026-11-04",
        "service_required": "Cremation",
    }
    lines = [
        {
            "category": f"Expense {i}",
            "description": f"Service {i}",
            "method": ["eft", "cash", "card"][i % 3],
            "amount": "10.00",
        }
        for i in range(10)
    ]
    response = client.put(
        f"/api/requisitions/requests/{rid}", json={"details": details, "lines": lines}
    )
    assert response.status_code == 200, response.text
    assert client.post(f"/api/requisitions/requests/{rid}/submit").status_code == 200
    from app.models.requisitions import RequisitionTransaction

    with Session(engine) as db:
        for i in range(73):
            db.add(
                RequisitionTransaction(
                    month_id=mid,
                    requisition_id=rid,
                    client_key=str(uuid4()),
                    transaction_date=date(2026, 11, 4),
                    kind="funding" if i == 0 else "card",
                    supplier="Example",
                    description="Extended ledger",
                    amount_cents=100000 if i == 0 else 1,
                    actor_id=1,
                    actor_name="User 1",
                    receipt_name="test.pdf",
                    receipt_mime="application/pdf",
                    receipt_content=book_pdf(),
                )
            )
        db.commit()
    wb = load_workbook(
        BytesIO(client.get(f"/api/requisitions/months/{mid}/workbook").content)
    )
    form = wb["Rekwisisie Vorm - 1"]
    assert form["B15"].value == details["id_number"]
    assert form["B15"].data_type == "s" and form["B15"].number_format == "@"
    assert form["B16"].value.date() == date(2026, 11, 1)
    assert form["B17"].value.date() == date(2026, 11, 4)
    assert form["B18"].value == "Cremation"
    assert form["A28"].value == "Expense 0"
    assert form["B28"].value == "Service 0 (EFT)"
    assert form["D38"].value == "=SUM(D28:D37)"
    assert len(form._images) == 1 and len(wb.active._images) == 2
    assert wb.active["K84"].value == "=K83"
    assert wb.active["K83"].value == "=K82+G83-I83-J83"
    assert wb.active["I84"].value == "=SUM(I11:I83)"


def test_unpriced_and_zero_amount_items_stay_editable_but_never_enter_the_emailed_pdf(
    system,
):
    from pypdf import PdfReader

    client, engine, actor = system
    mid, rid, _ = create_case(client)
    initial = client.get(f"/api/requisitions/requests/{rid}").json()
    assert initial["number"].startswith("REQ-1-2026-") and initial["revision"] == 0
    lines = [
        {
            "category": "Flowers",
            "description": "Priced flowers",
            "method": "card",
            "amount": "15.25",
        },
        {
            "category": "Other",
            "description": "UNPRICED_SPECIAL",
            "method": "eft",
            "amount": None,
        },
        {
            "category": "Schedule B",
            "description": "ZERO_AMOUNT_ITEM",
            "method": "cash",
            "amount": "0.00",
        },
        {"category": "Canvas", "description": "", "method": "card", "amount": None},
    ]
    response = client.put(
        f"/api/requisitions/requests/{rid}",
        json={"details": {}, "lines": lines, "expected_revision": 0},
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["lines"]) == 4 and response.json()["total_cents"] == 1525
    response = client.post(f"/api/requisitions/requests/{rid}/submit")
    assert (
        response.status_code == 200 and response.json()["number"] == initial["number"]
    )
    assert response.json()["revision"] == 1
    with Session(engine) as db:
        message = db.scalar(select(RequisitionEmail))
        text = "\n".join(
            page.extract_text() for page in PdfReader(BytesIO(message.document)).pages
        )
        assert "Priced flowers" in text and "15.25" in text
        assert (
            "UNPRICED_SPECIAL" not in text
            and "ZERO_AMOUNT_ITEM" not in text
            and "Canvas" not in text
        )
        wb = load_workbook(BytesIO(message.workbook))
        form = wb["Rekwisisie Vorm - 1"]
        assert form["A28"].value == "Flowers" and form["D28"].value == 15.25
        assert form["A29"].value is None and form["D29"].value is None


def test_employee_can_revise_submitted_form_with_same_number_and_preserved_history(
    system,
):
    from app.models.requisitions import RequisitionRevision
    from pypdf import PdfReader

    client, engine, actor = system
    mid, unused, bid = create_case(client)
    client.delete(f"/api/requisitions/requests/{unused}")
    for uid in (2, 3):
        assert (
            client.put(
                "/api/requisitions/grants", json={"user_id": uid, "enabled": True}
            ).status_code
            == 200
        )
    actor[0] = 2
    payload = {"month_id": mid, "book_id": bid, "request_date": "2026-11-03"}
    initial = client.post("/api/requisitions/requests", json=payload).json()
    rid = initial["id"]
    number = initial["number"]
    assert number.startswith("REQ-2-2026-") and initial["employee_id"] == 2
    assert (
        client.post("/api/requisitions/requests", json=payload).json()["number"]
        == number
    )
    body = {
        "details": {},
        "lines": [
            {
                "category": "Flowers",
                "description": "Employee flowers",
                "method": "card",
                "amount": "100.00",
            },
            {
                "category": "Other",
                "description": "NEEDS_AMOUNT_LATER",
                "method": "eft",
                "amount": None,
            },
        ],
        "expected_revision": 0,
    }
    assert client.put(f"/api/requisitions/requests/{rid}", json=body).status_code == 200
    assert (
        client.post(f"/api/requisitions/requests/{rid}/submit").json()["revision"] == 1
    )
    actor[0] = 3
    body["expected_revision"] = 1
    body["lines"][0]["amount"] = "123.45"
    assert client.put(f"/api/requisitions/requests/{rid}", json=body).status_code == 403
    actor[0] = 1
    assert client.post(f"/api/requisitions/months/{mid}/close").status_code == 200
    actor[0] = 2
    response = client.put(f"/api/requisitions/requests/{rid}", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 2 and response.json()["number"] == number
    assert client.put(f"/api/requisitions/requests/{rid}", json=body).status_code == 409
    body["expected_revision"] = 2
    assert (
        client.put(f"/api/requisitions/requests/{rid}", json=body).json()["revision"]
        == 2
    )
    with Session(engine) as db:
        history = db.scalars(
            select(RequisitionRevision)
            .where(RequisitionRevision.requisition_id == rid)
            .order_by(RequisitionRevision.revision)
        ).all()
        assert [json.loads(h.snapshot)["total_cents"] for h in history] == [
            10000,
            12345,
        ]
        documents = [
            e
            for e in db.scalars(select(RequisitionEmail).order_by(RequisitionEmail.id))
            if e.document
        ]
        assert len(documents) == 2
        texts = [
            "\n".join(p.extract_text() for p in PdfReader(BytesIO(e.document)).pages)
            for e in documents
        ]
        assert "100.00" in texts[0] and "Revision: 1" in texts[0]
        assert "123.45" in texts[1] and "Revision: 2" in texts[1]
        assert all("NEEDS_AMOUNT_LATER" not in t for t in texts)
        assert db.get(RequisitionMonth, mid).closing_cents == 50000


def test_outbox_delivery_does_not_resend_sent_or_uncertain(system, monkeypatch):
    client, engine, actor = system
    mid, rid, _ = create_case(client)
    client.post(f"/api/requisitions/requests/{rid}/submit")
    from app.db import session
    from app.services import email_service
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(session, "SessionLocal", sessionmaker(bind=engine))
    delivered = []

    def send(to, subject, message, **kwargs):
        delivered.append((to, kwargs))
        return "sent", datetime.utcnow(), None, {}

    monkeypatch.setattr(email_service, "send_smtp_email", send)
    # Recover the real implementation replaced in the fixture.
    import importlib

    real = importlib.reload(service).deliver_pending
    real()
    real()
    assert len(delivered) == 1
    assert delivered[0][0] == "wjm@martinsdirect.com"
    assert len(delivered[0][1]["attachments"]) == 2


def test_unsent_email_retries_but_uncertain_smtp_delivery_is_held(system, monkeypatch):
    client, engine, actor = system
    mid, rid, _ = create_case(client)
    client.post(f"/api/requisitions/requests/{rid}/submit")
    from app.db import session
    from app.services import email_service
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(session, "SessionLocal", sessionmaker(bind=engine))
    import importlib

    real = importlib.reload(service).deliver_pending
    monkeypatch.setattr(
        email_service,
        "send_smtp_email",
        lambda *a, **kw: ("pending", None, "SMTP not configured", {}),
    )
    real()
    with Session(engine) as db:
        item = db.scalar(select(RequisitionEmail))
        assert item.status == "pending"
        assert item.attempts == 1
        item.next_attempt_at = datetime(2020, 1, 1)
        db.commit()
    monkeypatch.setattr(
        email_service,
        "send_smtp_email",
        lambda *a, **kw: (
            "failed",
            None,
            "Delivery acknowledgement lost",
            {"delivery_uncertain": True},
        ),
    )
    real()
    real()
    with Session(engine) as db:
        item = db.scalar(select(RequisitionEmail))
        assert item.status == "uncertain"
        assert item.attempts == 2


def test_discarding_an_accidental_draft_allows_month_close_but_submitted_records_remain(
    system,
):
    client, engine, actor = system
    mid, rid, _ = create_case(client)
    assert client.delete(f"/api/requisitions/requests/{rid}").status_code == 200
    assert client.post(f"/api/requisitions/months/{mid}/close").status_code == 200


def test_migration_creates_the_complete_model_contract():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    from app.models.requisitions import TABLES

    engine = create_engine("sqlite://")
    names = {t.name for t in TABLES}
    Base.metadata.create_all(
        engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in names]
    )
    with engine.begin() as connection:
        for name in ("030_requisitions", "031_requisition_revisions"):
            path = Path(__file__).parents[1] / f"alembic/versions/{name}.py"
            spec = importlib.util.spec_from_file_location(name, path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
    inspector = inspect(engine)
    for table in TABLES:
        assert {c["name"] for c in inspector.get_columns(table.name)} == {
            c.name for c in table.columns
        }
