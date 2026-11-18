"""Populate the supplied Northcliff layout without inheriting its stale formulas."""

from copy import copy, deepcopy
from datetime import date
from io import BytesIO
import json
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment
from sqlalchemy import select

from app.models.requisitions import Requisition, RequisitionBook, RequisitionTransaction
from app.services.requisitions import priced_lines

TEMPLATE = Path(__file__).parents[1] / "templates" / "requisitions.xlsx"
MONEY = '"R "#,##0.00;[Red]-"R "#,##0.00'


def text_cell(sheet, address, value):
    cell = sheet[address]
    cell.value = str(value or "")
    cell.data_type = "s"  # An employee's text must never become an Excel formula.
    cell.number_format = "@"
    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)


def date_cell(sheet, address, value):
    try:
        value = date.fromisoformat(str(value))
    except (ValueError, TypeError):
        text_cell(sheet, address, value)
        return
    sheet[address] = value
    sheet[address].number_format = "dd/mm/yyyy"
    sheet[address].alignment = Alignment(horizontal="left", vertical="top")


def payment_form(wb, prototype, images, month, branch_name, req, book, index):
    form = wb.copy_worksheet(prototype)
    form.title = f"Rekwisisie Vorm - {index}"
    if req:
        text_cell(form, "A9", f"Rekwisisie Vorm - Revision {req.revision}")
    for data, anchor, width, height in images:
        image = Image(BytesIO(data))
        image.anchor = deepcopy(anchor)
        image.width = width
        image.height = height
        form.add_image(image)
    # These blank lines in the source accommodate the branch and author required
    # by the application. Keep the original deceased and payment field positions.
    for row in (11, 12, 14, 15, 16, 17, 18, 19):
        if row == 14:
            form["D14"] = None  # Remove the source's [42] placeholder.
        form.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    text_cell(form, "A12", "Branch / Tak:")
    text_cell(form, "B12", branch_name)
    text_cell(form, "A19", "Employee / Werknemer:")
    text_cell(form, "B19", req.employee_name if req else "")
    request_font = copy(form["D10"].font)
    # The source's short D1 number occupied D10; use its adjacent blank space
    # so the application's globally unique number remains readable on one line.
    form["D10"] = None
    form.merge_cells("C10:D10")
    text_cell(form, "C10", req.number if req else "")
    form["C10"].font = request_font
    form["C10"].alignment = Alignment(horizontal="right", vertical="top")
    form.row_dimensions[10].height = 30
    date_cell(form, "B10", req.request_date if req else "")
    text_cell(form, "B11", book.reference if book else "")
    text_cell(form, "B14", book.deceased if book else "")
    details = json.loads(req.details) if req else {}
    text_cell(form, "B15", details.get("id_number"))
    date_cell(form, "B16", details.get("date_of_death", ""))
    date_cell(form, "B17", details.get("funeral_date", ""))
    text_cell(form, "B18", details.get("service_required"))
    extra = "\n".join(
        f'{k.replace("_"," ").title()}: {v}'
        for k, v in details.items()
        if v
        and k not in {"id_number", "date_of_death", "funeral_date", "service_required"}
    )
    text_cell(form, "A20", "Additional details:")
    form.merge_cells("B20:D24")
    text_cell(form, "B20", extra)
    lines = sorted(
        priced_lines(req) if req else [],
        key=lambda line: {"eft": 0, "cash": 1, "card": 2}[line["method"]],
    )
    count = max(7, len(lines))
    extra_rows = count - 7
    if extra_rows:
        form.insert_rows(35, extra_rows)
        for row in range(35, 35 + extra_rows):
            for col in range(1, 5):
                form.cell(row, col)._style = copy(form.cell(34, col)._style)
            form.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
    for row in range(28, 28 + count):
        line = lines[row - 28] if row - 28 < len(lines) else None
        text_cell(
            form,
            f"A{row}",
            line.get("category") or line["method"].upper() if line else "",
        )
        text_cell(
            form,
            f"B{row}",
            f"{line['description']} ({line['method'].upper()})" if line else "",
        )
        form[f"D{row}"] = line["amount_cents"] / 100 if line else None
        form[f"D{row}"].number_format = MONEY
        form.row_dimensions[row].height = (
            max(25, 15 * ((len(line["description"]) // 55) + 1)) if line else 25
        )
    total = 35 + extra_rows
    form[f"D{total}"] = f"=SUM(D28:D{total-1})"
    form[f"D{total}"].number_format = MONEY
    form.print_area = f"A1:D{42+extra_rows}"
    form.print_options.horizontalCentered = True
    form.page_setup.orientation = "portrait"
    form.page_setup.paperSize = form.PAPERSIZE_A4
    form.page_setup.fitToWidth = 1
    form.page_setup.fitToHeight = 0
    form.sheet_properties.pageSetUpPr.fitToPage = True
    return form


def export_workbook(db, month, branch_name, blank=False):
    wb = load_workbook(TEMPLATE, keep_links=False)
    ledger = wb["KAART TRANSAKSIES"]
    prototype = wb["Rekwisisie Vorm - 1"]
    # copy_worksheet preserves cells/styles/merges, but not drawings. Capture the
    # supplied logo once, then create independent image streams for each form.
    images = [
        (i._data(), deepcopy(i.anchor), i.width, i.height) for i in prototype._images
    ]
    originals = list(wb.worksheets)
    transactions = (
        []
        if blank
        else db.scalars(
            select(RequisitionTransaction)
            .where(RequisitionTransaction.month_id == month.id)
            .order_by(
                RequisitionTransaction.transaction_date, RequisitionTransaction.id
            )
        ).all()
    )
    requests = (
        []
        if blank
        else db.scalars(
            select(Requisition)
            .where(Requisition.month_id == month.id, Requisition.status == "submitted")
            .order_by(Requisition.id)
        ).all()
    )
    # The ledger stays first, as in the source's selected opening tab.
    for sheet in originals:
        if sheet != ledger and sheet != prototype:
            wb.remove(sheet)
    for index, req in enumerate(requests if requests else [None] * 3, 1):
        book = db.get(RequisitionBook, req.book_id) if req else None
        # Avoid a title collision with the original prototype.
        if index == 1:
            prototype.title = "_Source Form"
        payment_form(wb, prototype, images, month, branch_name, req, book, index)
    wb.remove(prototype)
    if "I83:J83" in ledger.merged_cells:
        ledger.unmerge_cells("I83:J83")
    extra_rows = max(0, len(transactions) - 71)
    if extra_rows:
        ledger.insert_rows(82, extra_rows)
        for row in range(82, 82 + extra_rows):
            for col in range(1, 14):
                ledger.cell(row, col)._style = copy(ledger.cell(81, col)._style)
    last = max(81, 10 + len(transactions))
    totals = last + 1
    text_cell(ledger, "G3", month.month)
    text_cell(ledger, "G4", branch_name)
    text_cell(ledger, "G5", month.holder)
    ledger["C10"] = "Brought Forward Balance"
    ledger["F10"] = "Brought forward from last month"
    ledger["K10"] = 0 if blank else month.opening_cents / 100
    ledger["K10"].number_format = MONEY
    text_cell(ledger, "L9", "Cash")
    text_cell(ledger, "M9", "Receipt")
    for address in ("L9", "M9"):
        ledger[address]._style = copy(ledger["J9"]._style)
    ledger.column_dimensions["L"].width = 17
    ledger.column_dimensions["M"].width = 30
    ledger.column_dimensions["H"].width = 24
    # Replace every template formula, including its incorrect row-59/69/81 links
    # and SUMIF logic which would count purchase amounts as reimbursements.
    for row in range(11, last + 1):
        for col in range(1, 14):
            ledger.cell(row, col).value = None
        ledger.cell(row, 1, row - 10)
        ledger.cell(row, 11, f"=K{row-1}+G{row}-I{row}-J{row}-L{row}")
        for col in (7, 9, 10, 11, 12):
            ledger.cell(row, col).number_format = MONEY
    for row, t in enumerate(transactions, 11):
        req = db.get(Requisition, t.requisition_id)
        book = db.get(RequisitionBook, req.book_id)
        date_cell(ledger, f"B{row}", t.transaction_date)
        for col, value in {
            "C": {
                "funding": "Card Reimbursement",
                "allocation": "Requisition amount",
                "card": "Card Transaction",
                "eft": "EFT",
                "cash": "Cash Paid",
                "cash_payment": "Cash Paid",
            }[t.kind],
            "D": t.actor_name,
            "E": t.supplier,
            "F": f"{t.description}\nMF: {book.reference}",
            "H": req.number,
            "M": t.receipt_name,
        }.items():
            text_cell(ledger, f"{col}{row}", value)
        for col, kinds in [
            ("G", {"funding", "allocation"}),
            ("I", {"card"}),
            ("J", {"eft"}),
            ("L", {"cash", "cash_payment"}),
        ]:
            ledger[f"{col}{row}"] = t.amount_cents / 100 if t.kind in kinds else 0
        if (
            t.kind == "cash"
        ):  # Preserve balances of older, separately funded cash entries.
            ledger[f"K{row}"] = f"=K{row-1}+G{row}-I{row}-J{row}"
        ledger.row_dimensions[row].height = max(
            30, 15 * ((len(t.description) // 30) + 2)
        )
    ledger[f"F{totals}"] = "TOTALS"
    for col in ("G", "I", "J", "L"):
        ledger[f"{col}{totals}"] = f"=SUM({col}11:{col}{last})"
    ledger[f"K{totals}"] = f"=K{last}"
    for col in ("G", "I", "J", "K", "L"):
        ledger[f"{col}{totals}"].number_format = MONEY
    ledger.merge_cells(
        start_row=totals + 1, start_column=9, end_row=totals + 1, end_column=10
    )
    # Requested values are disclosed below the posted ledger, never credited.
    ledger.merge_cells(
        start_row=totals + 3, start_column=1, end_row=totals + 3, end_column=13
    )
    text_cell(
        ledger,
        f"A{totals+3}",
        "Submitted requisitions (included in the register above)",
    )
    for row, req in enumerate(requests, totals + 4):
        ledger.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
        text_cell(ledger, f"A{row}", req.number)
        text_cell(ledger, f"F{row}", "Requisition total")
        ledger[f"G{row}"] = req.total_cents / 100
        ledger[f"G{row}"].number_format = MONEY
    ledger.freeze_panes = "F11"
    # Finalised exports have no input dropdowns pointing at the source's obsolete
    # staff lists. The web forms enforce the live branch/staff/payment choices.
    ledger.data_validations.dataValidation = []
    ledger.print_area = f"A1:M{max(totals+1,totals+3+len(requests))}"
    ledger.print_title_rows = "9:10"
    ledger.page_setup.orientation = "landscape"
    ledger.page_setup.paperSize = ledger.PAPERSIZE_A3
    ledger.page_setup.fitToWidth = 1
    ledger.page_setup.fitToHeight = 0
    ledger.sheet_properties.pageSetUpPr.fitToPage = True
    notes = wb.create_sheet("Instruksies")
    notes.append(["Requisitions — current system workflow"])
    for line in [
        "Balance = opening balance + submitted requisitions - card, EFT and cash payments.",
        "Submission adds the total automatically. Revisions post only the difference.",
        "Older separately funded cash records retain their original accounting treatment.",
        "Submission emails the requisition PDF to wjm@martinsdirect.com. Blank and zero items are omitted.",
        "Every posting requires receipt/payment proof stored under the branch in Attendance.",
        "The next monthly register carries the previous closing balance automatically.",
        "Monthly card reports are emailed on the 30th at 17:00 South African time (February: last day).",
    ]:
        notes.append([line])
    notes.column_dimensions["A"].width = 110
    for row in notes:
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        notes.row_dimensions[row[0].row].height = 32
    wb.active = 0
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
