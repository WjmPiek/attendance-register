"""Parse the printed register and price removals without guessing staff identities."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
import re
import unicodedata

from dateutil.easter import easter
from pypdf import PdfReader


RATE_KEYS = ('driver_in', 'driver_out', 'assistant_in', 'assistant_out',
             'driver_sunday_holiday', 'assistant_sunday_holiday', 'driver_other_branch', 'assistant_other_branch') + tuple(f'{role}_{item}' for role in ('driver', 'assistant') for item in ('grave_service','full_funeral_service','cremation_service','church_service','joinings','overtime','invoice_commission'))
DEFAULT_WEEK = [{'start': '08:00', 'end': '17:00'} for _ in range(5)] + [{'start': '08:00', 'end': '13:00'}]


def normalise(value):
    value = unicodedata.normalize('NFKD', value or '')
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', value.encode('ascii', 'ignore').decode().lower()).split())


def driver_names(value):
    return [x.strip() for x in re.split(r'\s+(?:and|en)\s+|\s*[&,;/+]\s*|\n', value, flags=re.I) if x.strip()]


def match_employee(name, employees):
    key = normalise(name)
    exact = [e for e in employees if normalise(e['full_name']) == key]
    if len(exact) == 1:
        return exact[0]['user_id']
    candidates = [e for e in employees if normalise(e['full_name']).split(' ')[0] == key]
    return candidates[0]['user_id'] if len(candidates) == 1 else None


def parse_date(value):
    for fmt in ('%d %b %Y', '%d %B %Y', '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError('Unrecognised date: ' + value)


def parse_register_text(value):
    # The printed ID Number label can wrap onto two lines.
    value = re.sub(r'\bID[ \t]*\n[ \t]*Number[ \t]+', 'ID Number ', value, flags=re.I)
    if 'MORTUARY BOOK' not in value.upper():
        raise ValueError('This page is not a Mortuary Book register.')
    lines = [' '.join(x.split()) for x in value.splitlines() if x.strip()]
    references = {line.split()[2] for line in lines if line.lower().startswith('mf number ') and len(line.split()) > 2}
    if len(references) != 1:
        raise ValueError('Each page must contain exactly one Mortuary Book record.')

    def field(label, stop=None):
        for line in lines:
            if line.lower().startswith(label.lower() + ' '):
                result = line[len(label):].strip()
                return re.split(r'\s+' + re.escape(stop) + r'\b', result, maxsplit=1, flags=re.I)[0].strip() if stop else result
        return ''

    def trailing(label):
        for line in lines:
            match = re.search(r'\b' + re.escape(label) + r'\s+(.+)$', line, re.I)
            if match:
                return match.group(1).strip()
        return ''

    record = {
        'branch': field('Branch Name', 'Date Generated'),
        'reference': field('MF Number', 'Body Number'),
        'service_date': trailing('Date Generated'),
        'deceased': field('Name and Surname of Deceased'),
        'id_number': re.sub(r'\s+', '', field('ID Number', 'Age')),
        'collected_at': field('Collected At'),
        'driver_in': field('Driver In'),
        'driver': field('Driver'),
        'date_in': field('Date In', 'Time In'),
        'time_in': trailing('Time In').replace('h', ':').replace('H', ':'),
    }
    for key in ('branch', 'reference', 'service_date', 'driver_in', 'date_in', 'time_in'):
        if not record[key]:
            raise ValueError('Required field missing: ' + key.replace('_', ' '))
    if len(record['reference']) > 255 or len(record['branch']) > 255:
        raise ValueError('Reference or branch is too long.')
    record['service_date'] = parse_date(record['service_date'])
    record['date_in'] = parse_date(record['date_in'])
    record['time_in'] = time.fromisoformat(record['time_in']).strftime('%H:%M')
    record['names'] = driver_names(record['driver_in'])
    if not 1 <= len(record['names']) <= 10:
        raise ValueError('Check the Driver In names on this page.')
    return record


def parse_pdf(data):
    if not data.lstrip().startswith(b'%PDF-'):
        raise ValueError('Upload a PDF file.')
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise ValueError('Password-protected PDFs are not supported.')
    if not 1 <= len(reader.pages) <= 50:
        raise ValueError('Each PDF must have between 1 and 50 pages.')
    from app.services.pdf_records import parse_document_pages
    return parse_document_pages(reader, parse_register_text, 'mortuary')


def public_holidays(year):
    # Public Holidays Act, including the Monday after a Sunday holiday.
    days = {date(year, m, d) for m, d in ((1, 1), (3, 21), (4, 27), (5, 1), (6, 16), (8, 9), (9, 24), (12, 16), (12, 25), (12, 26))}
    days.update((easter(year) - timedelta(days=2), easter(year) + timedelta(days=1)))
    days.update(d + timedelta(days=1) for d in list(days) if d.weekday() == 6)
    # Exceptional proclaimed holidays; future dates can be added in settings.
    special = {date(2023, 12, 15), date(2024, 5, 29), date(2022, 12, 27), date(2019, 5, 8), date(2016, 8, 3), date(2014, 5, 7), date(2011, 5, 18), date(2009, 4, 22)}
    return days | {d for d in special if d.year == year}


def price_removal(record, role, policy, extra_holidays=(), other_branch=False, staff_hours=None):
    day = date.fromisoformat(record['date_in'])
    at = time.fromisoformat(record['time_in'])
    holiday = day in public_holidays(day.year)
    business = False
    if day.weekday() != 6 and not holiday:
        from app.services.staff_hours import work_window
        window = work_window(staff_hours, day.weekday()) if staff_hours is not None else policy['week'][day.weekday()]
        if window is not None:
            start, end = time.fromisoformat(window['start']), time.fromisoformat(window['end'])
            if start == end:
                raise ValueError('Staff working hours must have different start and end times. Correct them in Edit Staff.')
            business = start <= at < end if start < end else at >= start or at < end
    band = 'in' if business else 'out'
    sunday_holiday = day.weekday() == 6 or holiday
    category = 'sunday_holiday' if sunday_holiday else band
    rate = policy['rates'].get(f'{role}_{category}')
    if rate is None and sunday_holiday:
        rate = policy['rates'].get(f'{role}_out')
    additional = Decimal(str(policy['rates'].get(f'{role}_other_branch') or 0)) if other_branch else Decimal(0)
    base = Decimal(str(rate)) if rate is not None else None
    return {'band': band, 'fee_category': category,
            'fee_label': 'Sunday / public holiday' if sunday_holiday else 'Business hours' if business else 'After hours',
            'other_branch': bool(other_branch), 'additional_fee': str(additional.quantize(Decimal('0.01'))),
            'removal_base_fee': str(base.quantize(Decimal('0.01'))) if base is not None else None,
            'amount': str((base + additional).quantize(Decimal('0.01'))) if base is not None else None}
