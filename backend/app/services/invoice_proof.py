"""Read invoice totals without confusing them with individual payments."""
from datetime import datetime
from io import BytesIO
import re

from pypdf import PdfReader
from app.services.receipt_commissions import printed_money
from app.services.pdf_records import parse_document_pages, invoice_number_text


def parse_invoice_text(value):
    value = invoice_number_text(value)
    if not re.search(r'\b(?:TAX\s+)?INVOICE\b', value, re.I) or re.search(r'^\s*(?:KWITANSIE\s*/\s*RECEIPT|CREDIT\s+NOTE|QUOTATION)\s*$', value, re.I | re.M):
        raise ValueError('This page must be an original MF Invoice, not a receipt, quotation or credit note.')
    def field(pattern):
        match = re.search(pattern, value, re.I | re.M)
        return match.group(1).strip() if match else ''
    lines = [' '.join(line.split()) for line in value.splitlines() if line.strip()]
    headings = [i for i, line in enumerate(lines) if line.upper() == 'MARTINS FUNERALS']
    branch = field(r'\bBranch\s+Name[ \t]+(.+?)(?:[ \t]{2,}|$)') or (lines[headings[0] + 1] if headings and headings[0] + 1 < len(lines) else field(r'^MARTINS FUNERALS\s+(.+)$'))
    total_values = re.findall(r'(?<!Sub )\b(?:Invoice\s+Total(?:\s*\(?incl\.?\s*VAT\)?)?|Total\s+(?:Invoice\s+)?Amount(?:\s*\(?incl\.?\s*VAT\)?)?|Tot\s+Amnt|Grand\s+Total|TOTAL)[ \t]*[: ]?[ \t]*R?[ \t]*([\d, .]+)[ \t]*$', value, re.I | re.M)
    totals = {printed_money(amount) for amount in total_values}
    if len(totals) != 1 or next(iter(totals)) <= 0:
        raise ValueError('One unambiguous positive invoice total including VAT is required.')
    record = {
        'branch': branch,
        'reference': field(r'\bMF\s*(?:No\.?|Number|File\s*(?:No\.?|Number))[ \t]*[:.]?[ \t]*(\S+)'),
        'invoice_number': field(r'\b(?:Tax\s+)?Inv(?:oice)?\s*(?:Nr\.?|No\.?|Number)[ \t]*[:.]?[ \t]*(\S+)'),
        'deceased': field(r'\bDeceased\s+Name[ \t]+(.+?)(?:[ \t]{2,}|$)') or field(r'^\s*(?:Name\s+and\s+Surname\s+of\s+)?Deceased\s*:[ \t]*(.+)$'),
        'id_number': field(r'^ID\s*Num(?:ber)?\s*:\s*(.+)$'),
        'service_date': field(r'\bInvoice\s+Date[ \t]*:?[ \t]+(.+?)\s*$') or field(r'^\s*Date[ \t]*:?[ \t]+(.+)$'),
        'invoice_total': str(next(iter(totals))),
    }
    header = re.split(r'\bTO\s*:', value, maxsplit=1, flags=re.I)[0]
    printed_vat = re.search(r'\bVAT\s+Number[ \t]+([0-9]{10})\b', header, re.I)
    vat_number = printed_vat.group(1) if printed_vat else ''
    invalid_number = bool(re.search(r'VAT\s+Number[ \t]+[0-9]', header, re.I) and not vat_number)
    vat = re.search(r'\bVAT\s*\(([\d.]+)%\)[ \t]+R?[ \t]*([\d, .]+)[ \t]*$', value, re.I | re.M)
    subtotal_text = field(r'\bSub\s+Total[ \t]+R?[ \t]*([\d, .]+)[ \t]*$')
    subtotal = printed_money(subtotal_text) if subtotal_text else None
    vat_amount = printed_money(vat.group(2)) if vat else None
    record.update(vat_number=vat_number, vat_registered=bool(vat_number), vat_rate=vat.group(1) if vat else '0', vat_issue=None,
                  vat_amount=str(vat_amount or 0), invoice_subtotal=str(subtotal) if subtotal is not None else None)
    if vat_number:
        if subtotal is None or vat_amount is None or subtotal + vat_amount != next(iter(totals)):
            record.update(vat_issue='Printed VAT amounts do not reconcile; check branch VAT registration in the system.', commission_base=None)
        else:
            record['commission_base'] = str(subtotal)
    else:
        if vat_amount or (subtotal is not None and subtotal != next(iter(totals))):
            record.update(vat_issue='Printed VAT details are unclear; check branch VAT registration in the system.', commission_base=None, vat_registered=None)
        else:
            record['commission_base'] = record['invoice_total']
    if invalid_number:
        record.update(vat_registered=None, commission_base=None, vat_issue='Printed VAT number is invalid; check branch VAT registration in the system.')
    for key in ('branch', 'reference', 'invoice_number', 'deceased', 'service_date'):
        if not record[key] or len(record[key]) > 255:
            raise ValueError('Required invoice field missing or too long: ' + key.replace('_', ' '))
    for fmt in ('%d-%b-%y', '%d-%b-%Y', '%d %b %Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            record['service_date'] = datetime.strptime(record['service_date'], fmt).date().isoformat()
            break
        except ValueError:
            pass
    else:
        raise ValueError('Unrecognised invoice date.')
    return record


def parse_invoice_pdf(data):
    if not data.lstrip().startswith(b'%PDF-'):
        raise ValueError('Upload an original PDF invoice.')
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 50:
        raise ValueError('Use an unprotected invoice PDF with 1–50 pages.')
    return parse_document_pages(reader, parse_invoice_text, 'invoice', layout=True)
