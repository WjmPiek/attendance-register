from decimal import Decimal
from io import BytesIO
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import text

from app.api import receipt_commissions as api
from app.api.deps import get_current_user
from app.db.session import get_db
from app.services.invoice_proof import parse_invoice_text, parse_invoice_pdf
from app.services.receipt_commissions import require_payment_proof, resolve_commission_vat
from tests.test_mortuary_book import database, import_payload, quote_and_import
from tests.test_receipt_commissions import configure, receipt, stage_receipt, stage_invoice, calculate, OWNER


INVOICE = '''MF Number MFTEST-1315
Group Name       MARTINS FUNERALS EXAMPLE
Branch Name      EXAMPLE
Address          123 Example Road             Invoice Number     1309
                                               Invoice Date       07 Oct 2026
Telephone Number 0000000000                    VAT Number         4000000000
FUNERAL TAX INVOICE
TO:              Example Client
Deceased Name    Example Person
Deceased Address
Reference        Late Example Person
Insurance Amount: R 0.00
Client Pay in Amount: R 1 150.00
ANY AMOUNT TO BE PAID IN MUST BE PAID WITH A RECEIPT     Sub Total  R 1 000.00
VAT (15%)    R 150.00
Account must be paid prior to service.                TOTAL      R 1 150.00
'''


def pdf_bytes():
    stream = BytesIO(); pdf = canvas.Canvas(stream)
    for index, line in enumerate(INVOICE.splitlines()):
        pdf.drawString(20, 800 - index * 18, line)
    pdf.save(); return stream.getvalue()


def test_invoice_parser_uses_the_deceased_field_and_total_not_the_payer_or_subtotal():
    row = parse_invoice_text(INVOICE)
    assert row['branch'] == 'EXAMPLE' and row['deceased'] == 'Example Person'
    assert row['invoice_number'] == '1309' and row['invoice_total'] == '1150.00'
    assert row['commission_base'] == '1000.00' and row['vat_registered'] is True
    assert row['vat_number'] == '4000000000'


def test_non_vat_invoice_uses_full_amount():
    row = parse_invoice_text(INVOICE.replace('4000000000', '').replace('VAT (15%)    R 150.00', '').replace('R 1 000.00', 'R 1 150.00'))
    assert row['vat_registered'] is False and row['commission_base'] == '1150.00'


def test_inconsistent_printed_vat_is_retained_for_system_branch_resolution():
    row = parse_invoice_text(INVOICE.replace('R 150.00', 'R 100.00'))
    assert row['vat_issue'] and row['commission_base'] is None


def setup_case(db, total='1150.00'):
    configure(db)
    quote_and_import(db, import_payload())
    stage_invoice(db, total=total)


def test_instalments_unlock_only_after_full_payment_and_pay_once_per_invoice(database):
    setup_case(database)
    first = stage_receipt(database, [dict(receipt(), gross_received='500.00')])
    payload, quote = calculate(database, first['document_ids'])
    assert quote['total'] == '0' and all(r['state'] == 'blocked' for r in quote['items'])
    assert 'not fully paid' in quote['items'][0]['reason']
    assert api.settle(payload, OWNER, database)['created'] == 0
    # Reprinting the first receipt is not another R500 payment.
    stage_receipt(database, [dict(receipt(), gross_received='500.00')])
    assert database.execute(text("SELECT COUNT(*) FROM commission_documents WHERE kind='receipt'")).scalar() == 1
    final = stage_receipt(database, [dict(receipt(), receipt_number='PAY-2', gross_received='650.00')])
    payload, quote = calculate(database, final['document_ids'])
    ready = [r for r in quote['items'] if r['state'] == 'ready']
    assert len(ready) == 4
    assert {r['total_received'] for r in ready} == {'1150.00'}
    assert {r['base_amount'] for r in ready if r['category'] == 'invoice_commission'} == {'1000.00'}
    assert api.settle(payload, OWNER, database)['created'] == 4
    amounts = database.execute(text("SELECT calculated_amount FROM commission_entries WHERE commission_type='invoice_commission' ORDER BY employee_user_id")).scalars().all()
    assert [Decimal(str(amount)) for amount in amounts] == [Decimal('20'), Decimal('30')]
    # A later payment does not produce a second invoice or removal award.
    extra = stage_receipt(database, [dict(receipt(), receipt_number='PAY-3', gross_received='100.00')])
    payload, _ = calculate(database, extra['document_ids'])
    assert api.settle(payload, OWNER, database)['created'] == 0


def test_receipts_cannot_pay_without_the_invoice(database):
    configure(database); quote_and_import(database, import_payload())
    docs = stage_receipt(database, with_invoice=False)
    payload, quote = calculate(database, docs['document_ids'])
    assert all(r['state'] == 'blocked' for r in quote['items'])
    assert api.settle(payload, OWNER, database)['created'] == 0


@pytest.mark.parametrize('change', [{'deceased': 'Other Person'}, {'invoice_number': 'OTHER'}, {'reference': 'OTHER'}, {'branch': 'EXAMPLE SOUTH'}])
def test_all_three_document_identities_must_correspond(database, change):
    setup_case(database)
    docs = stage_receipt(database, [dict(receipt(), **change)], with_invoice=False)
    payload, quote = calculate(database, docs['document_ids'])
    assert all(r['state'] == 'blocked' for r in quote['items'])
    assert api.settle(payload, OWNER, database)['created'] == 0


def test_system_registered_branch_resolves_missing_invoice_vat_details(database):
    configure(database)
    row = parse_invoice_text(INVOICE.replace('R 150.00', 'R 100.00'))
    resolved = resolve_commission_vat(database, 2, 101, row)
    assert resolved['vat_registered'] and resolved['commission_base'] == '1000.00'
    assert resolved['vat_source'] == 'System branch VAT registration' and resolved['vat_notice']


def test_system_non_vat_branch_uses_full_amount_despite_conflicting_invoice(database):
    configure(database, False)
    resolved = resolve_commission_vat(database, 2, 101, parse_invoice_text(INVOICE))
    assert resolved['vat_registered'] is False and resolved['commission_base'] == '1150.00'


def test_unclear_invoice_and_unknown_system_vat_status_remain_blocked(database):
    row = parse_invoice_text(INVOICE.replace('R 150.00', 'R 100.00'))
    with pytest.raises(HTTPException, match='no confirmed branch VAT status'):
        resolve_commission_vat(database, 2, 101, row)


def test_changed_invoice_total_cannot_replace_an_existing_invoice(database):
    configure(database); stage_invoice(database, total='1150.00')
    with pytest.raises(HTTPException, match='different details'):
        stage_invoice(database, total='1200.00')


def client_for(db):
    app = FastAPI(); app.include_router(api.router, prefix='/api/receipt-commissions')
    identity = {'id': 1}
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=identity['id'])
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), identity


def test_invoice_upload_preserves_download_and_enforces_holder_scope(database):
    configure(database)
    client, identity = client_for(database)
    content = pdf_bytes()
    preview = client.post('/api/receipt-commissions/invoices/preview', files=[('files', ('invoice.pdf', content, 'application/pdf'))])
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert not data['errors'] and data['records'][0]['invoice_total'] == '1150.00'
    staged = client.post('/api/receipt-commissions/invoices/stage', json={'preview_token': data['preview_token'], 'confirmed_franchise': True})
    assert staged.status_code == 200, staged.text
    doc_id = staged.json()['document_ids'][0]
    url = f'/api/receipt-commissions/invoices/{doc_id}/download'
    assert client.get(url).content == content
    assert client.get(url).headers['content-type'] == 'application/pdf'
    identity['id'] = 99
    assert client.get(url).status_code in (403, 404)


def test_invoice_stage_cannot_use_an_unsigned_or_unconfirmed_preview(database):
    configure(database)
    client, _ = client_for(database)
    assert client.post('/api/receipt-commissions/invoices/stage', json={'preview_token': 'tampered', 'confirmed_franchise': True}).status_code == 400
    assert client.post('/api/receipt-commissions/invoices/stage', json={'preview_token': 'tampered'}).status_code == 400
