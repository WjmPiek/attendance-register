from io import BytesIO
from pypdf import PdfReader
from app.services.commission_pdf import build_commission_pdf
from app.services.receipt_commissions import COMMISSION_LABELS


def sample():
    rows=[]
    for bid,branch in [(1,'Northcliff'),(2,'Rivonia'),(3,'Benoni')]:
        for index,category in enumerate(list(COMMISSION_LABELS)[:8]):
            rows.append({'id':bid*100+index,'franchise_user_id':1,'earning_branch_id':bid,'branch_name':branch,
                'employee_user_id':10,'employee_name':'Alex Example','commission_type':category,
                'status':'approved','payment_eligible':True,'reference':f'MF{bid}001','service_date':'2026-11-03',
                'calculated_amount':str(10*bid),'source_metadata':'{}'})
    return rows


def test_cover_and_one_branch_per_page_include_full_category_person_and_mf_totals():
    rows=sample()
    pdf=build_commission_pdf(rows,[],period_start='2026-10-26',period_end='2026-11-25')
    pages=[page.extract_text() for page in PdfReader(BytesIO(pdf)).pages]
    assert len(pages)==4
    assert 'Cover - totals by manager / employee' in pages[0]
    assert 'Alex Example' in pages[0] and 'PERSON TOTAL' in pages[0]
    assert 'TOTAL APPROVED FOR FINANCE: R 480.00' in ' '.join(pages[0].split())
    for page,branch,bid in zip(pages[1:],['Benoni','Northcliff','Rivonia'],[3,1,2]):
        assert f'{branch} - branch commission details' in page
        assert f'MF{bid}001' in page
        for other in {'Benoni','Northcliff','Rivonia'}-{branch}:assert other not in page
        assert f'Branch approved total: R {80*bid:,.2f}' in ' '.join(page.split())
        assert 'Summary by manager / employee and category' in page
        assert 'Removals subtotal:' in page and 'Grave Service subtotal:' in page


def test_large_branch_continues_with_same_heading_without_omissions_or_sharing_next_branch():
    rows=[{**sample()[0],'id':index,'reference':f'MF{10000+index}'} for index in range(100)]
    rows.append({**sample()[0],'id':200,'earning_branch_id':2,'branch_name':'Rivonia','reference':'MF99999'})
    pages=[page.extract_text() for page in PdfReader(BytesIO(build_commission_pdf(rows,[]))).pages]
    north=[page for page in pages[1:] if 'Northcliff - branch commission details' in page]
    assert len(north)>1
    assert all('Rivonia' not in page for page in north)
    details='\n'.join(north)
    for index in range(100):assert details.count(f'MF{10000+index}\n')==1
    assert 'MF99999' in pages[-1]


def test_waiting_estimates_do_not_change_approved_totals_and_notes_are_retained():
    approved=[sample()[0]]
    pending=[{**sample()[1],'id':50,'status':'pending','payment_eligible':False,'expected_amount':'25',
              'carry_forward_notice':'Carried over from October into November','payment_block_reason':'Missing receipt'},
             {**sample()[2],'id':51,'status':'pending','payment_eligible':False,'estimate_available':False,'expected_amount':'0'}]
    pages=[page.extract_text() for page in PdfReader(BytesIO(build_commission_pdf(approved,pending))).pages]
    text=' '.join('\n'.join(pages).split())
    assert 'TOTAL APPROVED FOR FINANCE: R 10.00' in text
    assert 'Waiting to be finalised: R 25.00' in text
    assert 'PENDING - NOT APPROVED FOR PAYMENT' in text and 'Awaiting calculation' in text
    assert 'Carried over from October into November' in text and 'Missing receipt' in text


def test_duplicate_names_stay_separate_people_and_closed_items_are_not_payable():
    rows=[sample()[0],{**sample()[0],'id':2,'employee_user_id':11},
          {**sample()[0],'id':3,'status':'cancelled','calculated_amount':'999'}]
    text=PdfReader(BytesIO(build_commission_pdf(rows,[]))).pages[0].extract_text()
    assert text.count('PERSON TOTAL')==2
    assert 'TOTAL APPROVED FOR FINANCE: R 20.00' in ' '.join(text.split())
