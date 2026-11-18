"""Acceptance checks for the upload-first flow and monthly reporting."""

from datetime import date, datetime
from io import BytesIO
import json
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from openpyxl import load_workbook
from tests.test_requisitions import system, book_pdf, create_case, transaction
from app.models.core import User
from app.models.requisitions import (
    RequisitionMonth,
    RequisitionEmail,
    RequisitionMonthlyReport,
    RequisitionTransaction,
)
from app.services import requisition_workflow as workflow


@pytest.mark.parametrize("uid", [2, 3])
def test_active_commission_staff_can_share_book_without_finance_access(
    system, monkeypatch, uid
):
    client, engine, actor = system
    actor[0] = uid
    assert client.get("/api/requisitions/mortuary-access").json() == {"enabled": False}
    with Session(engine) as db:
        db.execute(
            text("INSERT INTO employee_commission_options VALUES(10,:uid,TRUE)"),
            {"uid": uid},
        )
        db.commit()
    staged = []
    monkeypatch.setattr(
        workflow, "stage_commission_book", lambda *args: staged.append(args[1:])
    )
    assert client.get("/api/requisitions/mortuary-access").json()["enabled"]
    for _ in range(2):
        result = client.post(
            "/api/requisitions/books/import",
            files={"file": ("book.pdf", book_pdf("Rivonia"), "application/pdf")},
        )
        assert result.status_code == 200, result.text
    assert result.json()["items"][0]["duplicate"]
    assert staged[0][0] == 10 and staged[0][1]["earning_branch_id"] == 102
    assert staged[0][2] == book_pdf("Rivonia")
    assert client.get("/api/requisitions/access").json()["enabled"] is False
    assert client.get("/api/requisitions/workflow/requests").status_code == 403
    assert (
        client.post(
            "/api/requisitions/workflow/start",
            json={"book_id": result.json()["items"][0]["id"]},
        ).status_code
        == 403
    )
    assert (
        client.get("/api/requisitions/mortuary-access?franchise_user_id=20").json()[
            "enabled"
        ]
        is False
    )
    assert (
        client.post(
            "/api/requisitions/books/import?franchise_user_id=20",
            files={"file": ("book.pdf", book_pdf(), "application/pdf")},
        ).status_code
        == 403
    )
    with Session(engine) as db:
        table = "employee_users" if uid == 2 else "manager_users"
        db.execute(
            text(f"UPDATE {table} SET is_active=FALSE WHERE user_id=:uid"), {"uid": uid}
        )
        db.commit()
    assert client.get("/api/requisitions/mortuary-access").json()["enabled"] is False


def test_upload_uses_printed_linked_branch_and_starts_employee_form(
    system, monkeypatch
):
    client, engine, actor = system
    client.put("/api/requisitions/grants", json={"user_id": 2, "enabled": True})
    actor[0] = 2
    staged = []
    monkeypatch.setattr(
        workflow, "stage_commission_book", lambda *args: staged.append(args[2])
    )
    result = client.post(
        "/api/requisitions/books/import?branch_id=101",
        files={"file": ("book.pdf", book_pdf("Rivonia"), "application/pdf")},
    )
    assert result.status_code == 200, result.text
    item = result.json()["items"][0]
    assert item["branch_id"] == 102 and staged[0]["branch"] == "Rivonia"
    result = client.post(
        "/api/requisitions/workflow/start", json={"book_id": item["id"]}
    )
    assert result.status_code == 200, result.text
    req = result.json()
    assert req["number"].startswith("REQ-2-") and req["employee_id"] == 2
    assert (
        req["branch_id"] == 102
        and req["reference"] == "MF123"
        and req["deceased"] == "Example Person"
    )
    assert req["details"]["id_number"] == "0000000000000"
    assert (
        client.post(
            "/api/requisitions/workflow/start", json={"book_id": item["id"]}
        ).json()["id"]
        == req["id"]
    )
    assert len(client.get("/api/requisitions/workflow/requests").json()) == 1
    assert (
        client.get("/api/requisitions/months?branch_id=102").json()[0]["opening_cents"]
        == 0
    )


def test_shared_book_stages_existing_commission_document_and_original(monkeypatch):
    from app.services import commission_files
    from app.api import receipt_commissions

    calls = []
    monkeypatch.setattr(
        commission_files, "store_file", lambda *args: calls.append(("file", args))
    )
    monkeypatch.setattr(
        receipt_commissions, "save_document", lambda *args: calls.append(("doc", args))
    )
    record = {"reference": "MF123", "source_hash": "abc", "pages": [1, 2]}
    workflow.stage_commission_book("db", 10, record, b"original", "book.pdf", 2)
    assert calls[0] == (
        "file",
        ("db", 10, "abc", "book.pdf", b"original", 2, "mortuary", 2),
    )
    assert calls[1] == ("doc", ("db", 10, "mortuary", record, [], 2))


def test_auto_register_rollover_carries_exact_balance(system):
    client, engine, actor = system
    mid, rid, _ = create_case(client)
    assert client.post(f"/api/requisitions/requests/{rid}/submit").status_code == 200
    assert (
        transaction(client, rid, "card", "50.25", day="2026-12-01").status_code == 200
    )
    with Session(engine) as db:
        old = db.get(RequisitionMonth, mid)
        new = db.scalar(
            select(RequisitionMonth).where(RequisitionMonth.month == "2026-12")
        )
        assert old.status == "closed" and old.closing_cents == 375000
        assert new.opening_cents == 375000
        assert workflow.service.balance(db, new) == 369975


def test_automatic_rollover_keeps_unsubmitted_forms_editable(system):
    from app.models.requisitions import Requisition

    client, engine, actor = system
    mid, rid, _ = create_case(client)
    original = client.get(f"/api/requisitions/requests/{rid}").json()["number"]
    with Session(engine) as db:
        month = workflow.ensure_month(db, 10, 101, date(2026, 12, 1), "Card holder", 1)
        db.commit()
        draft = db.get(Requisition, rid)
        assert draft.month_id == month.id and draft.number == original
    assert (
        client.put(
            f"/api/requisitions/requests/{rid}",
            json={
                "details": {},
                "lines": [
                    {"description": "Flowers", "method": "card", "amount": "50.00"}
                ],
            },
        ).status_code
        == 200
    )
    assert client.post(f"/api/requisitions/requests/{rid}/submit").status_code == 200


def test_revisions_credit_only_delta_and_payments_do_not_queue_emails(system):
    client, engine, actor = system
    mid, rid, _ = create_case(client)
    client.post(f"/api/requisitions/requests/{rid}/submit")
    body = {
        "details": {},
        "expected_revision": 1,
        "lines": [{"description": "Flowers", "method": "card", "amount": "100.00"}],
    }
    assert client.put(f"/api/requisitions/requests/{rid}", json=body).status_code == 200
    body["expected_revision"] = 2
    assert client.put(f"/api/requisitions/requests/{rid}", json=body).status_code == 200
    assert transaction(client, rid, "eft", "10.01").status_code == 200
    assert transaction(client, rid, "cash", "9.99").status_code == 200
    ledger = client.get(f"/api/requisitions/months/{mid}").json()
    assert ledger["balance_cents"] == 58000
    assert [
        t["amount_cents"] for t in ledger["transactions"] if t["kind"] == "allocation"
    ] == [325000, -315000]
    with Session(engine) as db:
        emails = db.scalars(select(RequisitionEmail)).all()
        assert len(emails) == 2 and all(not e.include_workbook for e in emails)
        assert all(e.recipient == "wjm@martinsdirect.com" for e in emails)
    wb = load_workbook(
        BytesIO(client.get(f"/api/requisitions/months/{mid}/workbook").content)
    )
    sheet = wb.active
    # Independently reconcile exported credit/debit columns to the displayed balance.
    calculated = sheet["K10"].value + sum(
        (sheet.cell(row, 7).value or 0)
        - (sheet.cell(row, 9).value or 0)
        - (sheet.cell(row, 10).value or 0)
        - (sheet.cell(row, 12).value or 0)
        for row in range(11, 15)
    )
    assert round(calculated * 100) == ledger["balance_cents"]


@pytest.mark.parametrize(
    "month,before,due",
    [
        ("2026-11", datetime(2026, 11, 30, 16, 59), datetime(2026, 11, 30, 17)),
        ("2027-02", datetime(2027, 2, 28, 16, 59), datetime(2027, 2, 28, 17)),
        ("2028-02", datetime(2028, 2, 29, 16, 59), datetime(2028, 2, 29, 17)),
    ],
)
def test_monthly_report_schedule_nomination_and_durable_once_only(
    system, month, before, due
):
    client, engine, actor = system
    assert (
        client.put(
            "/api/requisitions/report-settings",
            json={"recipient": "nominated@example.com"},
        ).status_code
        == 200
    )
    assert (
        client.get("/api/requisitions/report-settings").json()["recipient"]
        == "nominated@example.com"
    )
    assert (
        client.put(
            "/api/requisitions/report-settings", json={"recipient": "invalid"}
        ).status_code
        == 422
    )
    with Session(engine) as db:
        register = workflow.ensure_month(
            db, 10, 101, date.fromisoformat(month + "-01"), "Card holder", 1
        )
        db.commit()
        mid = register.id
        workflow.queue_monthly_reports(db, before)
        assert db.scalar(select(RequisitionEmail.id)) is None
        workflow.queue_monthly_reports(db, due)
        workflow.queue_monthly_reports(db, due)
        message = db.scalar(select(RequisitionEmail))
        assert (
            message.recipient == "nominated@example.com"
            and message.include_workbook
            and not message.document
        )
        assert message.workbook.startswith(b"PK")
        assert db.get(RequisitionMonthlyReport, mid).email_id == message.id
        assert len(db.scalars(select(RequisitionEmail)).all()) == 1
    actor[0] = 2
    assert client.get("/api/requisitions/report-settings").status_code == 403


def test_optional_client_details_are_read_from_mortuary_form():
    from app.services.mortuary import parse_register_text
    from pypdf import PdfReader

    content = PdfReader(BytesIO(book_pdf())).pages[0].extract_text()
    result = parse_register_text(
        content
        + "\nClient Name and Surname Example Client\nClient Contact Number 0123456789\nClient Address 12 Example Road\nDate of Death 01 Nov 2026\nFuneral Date 04 Nov 2026"
    )
    assert result["client_name"] == "Example Client"
    assert result["client_contact_number"] == "0123456789"
    assert result["client_address"] == "12 Example Road"
    assert (
        result["date_of_death"] == "2026-11-01"
        and result["funeral_date"] == "2026-11-04"
    )
