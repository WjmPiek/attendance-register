"""Synthetic print layouts; no customer documents or personal data in fixtures."""
from io import BytesIO

import pytest
from reportlab.pdfgen import canvas

from app.services.invoice_proof import parse_invoice_pdf
from app.services.mortuary import parse_pdf
from app.services.receipt_commissions import parse_receipt_pdf
from app.services.pdf_records import imported_page_count
from tests.test_invoice_payment_proof import INVOICE
from tests.test_mortuary_book import SAMPLE
from tests.test_receipt_commissions import RECEIPT


def pdf(*pages):
    stream=BytesIO()
    document=canvas.Canvas(stream)
    for content in pages:
        for index,line in enumerate(content.splitlines()):
            document.drawString(20,800-index*18,line)
        document.showPage()
    document.save()
    return stream.getvalue()


def test_invoice_verifies_vat_and_total_on_second_page_with_wrapped_number_label():
    first,last=INVOICE.split('VAT (15%)',1)
    first=first.replace('Invoice Number     1309','Invoice     1309\nAddress continuation                       Number')
    rows,errors=parse_invoice_pdf(pdf(first,'VAT (15%)'+last))
    assert errors==[] and len(rows)==1
    row=rows[0]
    assert row['pages']==[1,2] and row['invoice_number']=='1309'
    assert row['reference']=='MFTEST-1315' and row['branch']=='EXAMPLE'
    assert row['invoice_total']=='1150.00' and row['commission_base']=='1000.00'
    assert row['vat_amount']=='150.00' and row['vat_issue'] is None
    assert imported_page_count(rows)==2


def test_mortuary_continuation_contains_removal_details_and_wrapped_id():
    first,last=SAMPLE.split('Driver In',1)
    first=first.replace('ID Number 0000000000000','ID\nNumber 0000000000000')
    rows,errors=parse_pdf(pdf(first,'Driver In'+last))
    assert errors==[] and len(rows)==1
    assert rows[0]['pages']==[1,2] and rows[0]['names']==['Ewald','Aubrey']
    assert rows[0]['time_in']=='23:45' and rows[0]['id_number']=='0000000000000'


def test_mortuary_signature_and_legal_footer_are_part_of_the_original_record():
    rows,errors=parse_pdf(pdf(SAMPLE,'The Franchisor accepts no responsibility.\nAll Rights Reserved!'))
    assert errors==[] and len(rows)==1 and rows[0]['pages']==[1,2]


def test_receipt_payment_amount_on_continuation_is_verified():
    first,last=RECEIPT.split('Amnt Rcvd:',1)
    rows,errors=parse_receipt_pdf(pdf(first,'Amnt Rcvd:'+last))
    assert errors==[] and len(rows)==1
    assert rows[0]['pages']==[1,2] and rows[0]['gross_received']=='23580.61'


def test_two_two_page_invoices_do_not_share_totals_or_identity():
    first,last=INVOICE.split('VAT (15%)',1)
    second=first.replace('MFTEST-1315','MFTEST-9999').replace('1309','1310').replace('Example Person','Other Person')
    rows,errors=parse_invoice_pdf(pdf(first,'VAT (15%)'+last,second,'VAT (15%)'+last))
    assert errors==[] and [r['pages'] for r in rows]==[[1,2],[3,4]]
    assert [r['invoice_number'] for r in rows]==['1309','1310']
    assert [r['deceased'] for r in rows]==['Example Person','Other Person']


@pytest.mark.parametrize('tail', [
    'MF Number MFOTHER-1\nVAT (15%) R 150.00\nTOTAL R 1 150.00',
    'Branch Name OTHER\nVAT (15%) R 150.00\nTOTAL R 1 150.00',
    'Invoice Number 9999\nVAT (15%) R 150.00\nTOTAL R 1 150.00',
    'Deceased Name Other Person\nVAT (15%) R 150.00\nTOTAL R 1 150.00',
])
def test_conflicting_continuation_cannot_supply_another_cases_total(tail):
    first,_=INVOICE.split('VAT (15%)',1)
    rows,errors=parse_invoice_pdf(pdf(first,tail))
    assert rows==[] and len(errors)==1 and 'Conflicting' in errors[0]['error']


def test_missing_totals_cannot_be_borrowed_from_the_next_invoice():
    first,_=INVOICE.split('VAT (15%)',1)
    second=INVOICE.replace('MFTEST-1315','MFTEST-9999').replace('1309','1310')
    rows,errors=parse_invoice_pdf(pdf(first,second))
    assert len(rows)==1 and rows[0]['invoice_number']=='1310' and rows[0]['pages']==[2]
    assert len(errors)==1 and errors[0]['page']==1


def test_repeated_header_on_numbered_continuation_verifies_one_invoice():
    first,last=INVOICE.split('Insurance Amount:',1)
    rows,errors=parse_invoice_pdf(pdf(first,first+'\nPage 2 of 2\nInsurance Amount:'+last))
    assert errors==[] and len(rows)==1 and rows[0]['pages']==[1,2]
    assert rows[0]['invoice_total']=='1150.00'


def test_contradictory_totals_and_unreadable_pages_are_reported():
    rows,errors=parse_invoice_pdf(pdf(INVOICE,'TOTAL R 9 999.00'))
    assert rows==[] and len(errors)==1 and 'unambiguous' in errors[0]['error']
    rows,errors=parse_pdf(pdf(SAMPLE,'Unreadable unrelated page'))
    assert len(rows)==1 and len(errors)==1 and errors[0]['page']==2
