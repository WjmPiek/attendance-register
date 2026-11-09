"""Keep printed continuation pages with their document, not with another case."""
import re


def imported_page_count(items):
    return sum(len(item.get('pages') or [item.get('page')]) for item in items)


def invoice_number_text(value):
    # Some print layouts wrap the label below its value: "Invoice 1321" then
    # "Number". Repair that label without collapsing the invoice's columns.
    return re.sub(r'\bInvoice[ \t]+(\d+)(?=[ \t]*\n[^\n]*\bNumber\b)',
                  r'Invoice Number \1', value, flags=re.I)


def _values(value, pattern):
    return {re.sub(r'[^a-z0-9]', '', match.casefold())
            for match in re.findall(pattern, value, re.I | re.M) if match.strip()}


def verify_identity(value, kind):
    patterns = {
        'MF number': r'\bMF\s*(?:No\.?|Number|File\s*(?:No\.?|Number))[ \t]*[:.]?[ \t]*(\S+)',
        'branch': r'^[ \t]*Branch Name[ \t]+(.+?)(?:[ \t]{2,}|[ \t]+Date Generated\b|$)',
        'ID number': r'^[ \t]*ID\s*Num(?:ber)?[ \t]*:?[ \t]*(\d+)',
    }
    if kind == 'invoice':
        patterns.update({
            'invoice number': r'\b(?:Tax\s+)?Inv(?:oice)?\s*(?:Nr\.?|No\.?|Number)[ \t]*[:.]?[ \t]*(\S+)',
            'deceased': r'^[ \t]*Deceased Name[ \t]+(.+?)(?:[ \t]{2,}|$)',
        })
        value = invoice_number_text(value)
    elif kind == 'mortuary':
        patterns.update({
            'deceased': r'^[ \t]*Name and Surname of Deceased[ \t]+(.+?)\s*$',
            'driver in': r'^[ \t]*Driver In[ \t]+(.+?)\s*$',
            'date in': r'^[ \t]*Date In[ \t]+(.+?)(?:[ \t]+Time In\b|$)',
            'time in': r'\bTime In[ \t]+(\S+)',
        })
    else:
        patterns.update({
            'receipt number': r'^[ \t]*Receipt\s*(?:Nr\.?|No\.?)[ \t]*[:.]?[ \t]*(\S+)',
            'deceased': r'^[ \t]*Deceased[ \t]*:[ \t]*(.+?)\s*$',
            'payment amount': r'^[ \t]*(?:Amnt Rcvd|Amount Received|Total Received)[ \t]*:[ \t]*R?[ \t]*([\d, .]+)$',
        })
    for label, pattern in patterns.items():
        if len(_values(value, pattern)) > 1:
            raise ValueError(f'Conflicting {label} across document pages; check the original PDF.')


def parse_document_pages(reader, parser, kind, *, layout=False):
    starts = {
        'mortuary': r'\bMORTUARY BOOK\b',
        'invoice': r'\b(?:FUNERAL\s+)?(?:TAX\s+)?INVOICE\b',
        'receipt': r'\b(?:KWITANSIE\s*/\s*)?RECEIPT\b',
    }
    # Headings are stronger than incidental words in terms such as "this
    # invoice" or "must be paid with a receipt" on continuation pages.
    def starts_document(value):
        if kind == 'mortuary':
            return bool(re.search(starts[kind], value, re.I))
        return bool(re.search(r'^[ \t]*(?:Group Name[^\n]*?[ \t]{2,})?'
                              + starts[kind] + r'[ \t]*$', value, re.I | re.M))

    continuation = {
        'mortuary': r'\b(?:Franchisor|All Rights Reserved|SIGNATURE|PUTTING BODY IN|Driver In|Date In|Time In|Driver Out|Place of Burial|Death Certificate|Any Possessions|MF Number)\b',
        'invoice': r'\b(?:VAT\s*\(|Sub Total|Grand Total|TOTAL|BANK DETAILS|SIGNATURE|Invoice Number|MF Number|QTY|DESCRIPTION|AMOUNT|continued)\b',
        'receipt': r'\b(?:Amnt Rcvd|Amount Received|Total Received|Tot Amnt|Bal Due|SIGNATURE|BANK DETAILS|Receipt Nr|Receipt No|MF Number|continued)\b',
    }
    records, errors, pending = [], [], []

    def flush():
        if not pending:
            return
        pages = [number for number, _ in pending]
        try:
            value = '\n'.join(content for _, content in pending)
            verify_identity(value, kind)
            record = parser(value)
            record.update(page=pages[0], pages=pages)
            records.append(record)
        except (ValueError, TypeError) as exc:
            errors.append({'page': pages[0], 'pages': pages, 'error': str(exc)})
        pending.clear()

    for number, page in enumerate(reader.pages, 1):
        value = page.extract_text(extraction_mode='layout') if layout else page.extract_text()
        value = value or ''
        start = starts_document(value)
        repeated_header = False
        if not start:
            try:
                parser(value)
            except (ValueError, TypeError):
                pass
            else:
                start = True
        if start and pending:
            previous = '\n'.join(content for _, content in pending)
            pattern = r'\bMF\s*(?:No\.?|Number|File\s*(?:No\.?|Number))[ \t]*[:.]?[ \t]*(\S+)'
            references = _values(previous, pattern)
            # A repeated heading is a continuation only for the same case and
            # an unfinished document, or an explicitly numbered later page.
            if references and references == _values(value, pattern):
                try:
                    parser(previous)
                except (ValueError, TypeError):
                    start = False
                else:
                    if re.search(r'\b(?:continued|Page\s+[2-9]\d*\s+(?:of|/)\s*\d+)\b', value, re.I):
                        start = False
                repeated_header = not start
        if start:
            flush()
            pending.append((number, value))
        elif pending and (repeated_header or re.search(continuation[kind], value, re.I)) and (repeated_header or not re.search(
                r'^[ \t]*(?:KWITANSIE\s*/\s*RECEIPT|FUNERAL TAX INVOICE|MORTUARY BOOK REGISTER DETAILS|CREDIT NOTE|QUOTATION)[ \t]*$', value, re.I | re.M)):
            pending.append((number, value))
        else:
            flush()
            # Keep the existing per-page validation message for unrelated or
            # unreadable pages, and never borrow details across such a page.
            try:
                parser(value)
            except (ValueError, TypeError) as exc:
                errors.append({'page': number, 'error': str(exc)})
            else:
                errors.append({'page': number, 'error': 'Document heading missing; check the original PDF.'})
    flush()
    return records, errors
