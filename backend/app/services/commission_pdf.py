"""One commission statement layout for downloads and finance attachments."""
from collections import defaultdict
from decimal import Decimal
from io import BytesIO
import json
import re
from xml.sax.saxutils import escape

from app.services.receipt_commissions import COMMISSION_LABELS


def build_commission_pdf(approved, waiting, *, title='Commission statement', period_start='', period_end='', reference=''):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, NextPageTemplate, PageBreak, Paragraph, Spacer, Table, TableStyle

    purple=colors.HexColor('#69499b')
    styles=getSampleStyleSheet()
    for name,size,leading,extra in [('Cell',8,10,{}),('Money',8,10,{'alignment':TA_RIGHT}),
        ('Section',12,16,{'textColor':purple,'spaceBefore':12,'spaceAfter':6,'keepWithNext':True}),
        ('Category',10,12,{'textColor':purple,'spaceBefore':5,'spaceAfter':3,'keepWithNext':True}),
        ('Note',8,10,{'textColor':colors.HexColor('#586174'),'spaceAfter':3})]:
        styles.add(ParagraphStyle(name,fontName='Helvetica',fontSize=size,leading=leading,**extra))
    def p(value,style='Cell'):
        return Paragraph(escape(str(value if value is not None else '')).replace('\n','<br/>'),styles[style])
    def money(value):return f'R {Decimal(str(value or 0)):,.2f}'
    def label(category):return COMMISSION_LABELS.get(category,str(category).replace('_',' ').title())
    def amount(row,ready):
        if not ready and row.get('estimate_available') is False:return Decimal(0)
        return Decimal(str(row['calculated_amount'] if ready else row.get('expected_amount',row.get('calculated_amount',0)) or 0))
    def mf(value):
        value=re.split(r' / (?:Invoice|Receipt) ',str(value or ''),flags=re.I)[0].strip()
        return 'MF'+re.sub(r'^MF[\s-]*','',value,flags=re.I) if value else 'MF number unavailable'
    def table(values,widths,money_cols=()):
        result=Table([[p(value,'Money' if index in money_cols and row_index else 'Cell') for index,value in enumerate(row)] for row_index,row in enumerate(values)],
                     colWidths=[width*mm for width in widths],repeatRows=1,hAlign='LEFT')
        result.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eee8f5')),
            ('LINEBELOW',(0,0),(-1,0),.6,purple),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#ded7e8')),
            ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
            ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
        return result
    lines=[]
    for ready,rows in [(True,approved),(False,waiting)]:
        for source in rows:
            row=dict(source)
            if row.get('status','approved' if ready else 'pending') not in {'pending','approved'}:continue
            branch=row.get('service_branch') or row.get('branch_name') or 'Unspecified branch'
            person=row.get('employee_name') or 'Unspecified staff member'
            lines.append({'row':row,'ready':ready,'amount':amount(row,ready),'branch':branch,'person':person,
                'branch_key':(row.get('franchise_user_id'),row.get('earning_branch_id') or branch),
                'person_key':row.get('employee_user_id') or person,'category':row['commission_type']})
    def totals(items):
        return (sum((line['amount'] for line in items if line['ready']),Decimal(0)),
                sum((line['amount'] for line in items if not line['ready']),Decimal(0)))
    branches=defaultdict(list);people=defaultdict(list)
    for line in lines:
        branches[line['branch_key']].append(line);people[line['person_key']].append(line)
    ordered=sorted(branches.values(),key=lambda items:(items[0]['branch'].casefold(),str(items[0]['branch_key'])))
    stream=BytesIO()
    doc=BaseDocTemplate(stream,pagesize=A4,leftMargin=16*mm,rightMargin=16*mm,topMargin=28*mm,bottomMargin=17*mm,title=title)
    def page_header(section):
        def draw(canvas,document):
            canvas.saveState();canvas.setFillColor(purple);canvas.setFont('Helvetica-Bold',10)
            canvas.drawString(16*mm,282*mm,"MARTIN'S FUNERALS")
            heading=p(section,'Note');heading.wrap(doc.width,30*mm);heading.drawOn(canvas,16*mm,273*mm)
            canvas.setStrokeColor(colors.HexColor('#ded7e8'));canvas.line(16*mm,270*mm,194*mm,270*mm)
            canvas.setFont('Helvetica',8);canvas.drawString(16*mm,10*mm,reference or 'Commission statement')
            canvas.drawRightString(194*mm,10*mm,f'Page {document.page}');canvas.restoreState()
        return draw
    frame=lambda:Frame(doc.leftMargin,doc.bottomMargin,doc.width,doc.height,id='body',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id='cover',frames=[frame()],onPage=page_header('Cover - totals by manager / employee'))]+
        [PageTemplate(id=f'branch-{index}',frames=[frame()],onPage=page_header(items[0]['branch']+' - branch commission details')) for index,items in enumerate(ordered)])
    approved_total,waiting_total=totals(lines)
    story=[p(title,'Title'),p(f'Period: {period_start} to {period_end}','Note'),p(reference,'Note'),
        p('TOTAL APPROVED FOR FINANCE: '+money(approved_total),'Section'),
        p('Waiting to be finalised: '+money(waiting_total)),
        p('Waiting estimates are excluded from payment totals. Items awaiting calculation are excluded from estimate subtotals. This statement does not execute payroll.','Note'),
        p('Approved totals by manager / employee - all service branches','Section')]
    if not people:story.append(p('No commissions for the selected period and scope.'))
    for items in sorted(people.values(),key=lambda items:(items[0]['person'].casefold(),str(items[0]['person_key']))):
        story.append(p(items[0]['person'],'Category'))
        grouped=defaultdict(list)
        for line in items:grouped[(line['branch'],line['category'])].append(line)
        values=[['Branch','Commission category','Approved','Waiting estimate']]
        for (branch,category),entries in sorted(grouped.items()):
            approved_amount,waiting_amount=totals(entries)
            values.append([branch,label(category),money(approved_amount),money(waiting_amount)+(' + awaiting calculation' if any(not entry['ready'] and entry['row'].get('estimate_available') is False for entry in entries) else '')])
        a,w=totals(items);values.append(['PERSON TOTAL','',money(a),money(w)])
        story.extend([table(values,[46,66,33,33],(2,3)),Spacer(1,3*mm)])
    if waiting:story.append(p('PENDING - NOT APPROVED FOR PAYMENT','Category'))
    for index,items in enumerate(ordered):
        story.extend([NextPageTemplate(f'branch-{index}'),PageBreak(),p(items[0]['branch'],'Title')])
        a,w=totals(items)
        story.extend([p('Branch approved total: '+money(a),'Section'),p('Branch waiting estimate: '+money(w),'Note'),p('Summary by manager / employee and category','Category')])
        grouped=defaultdict(list)
        for line in items:grouped[(line['person_key'],line['person'],line['category'])].append(line)
        values=[['Manager / employee','Commission category','Approved','Waiting estimate']]
        for (_,person,category),entries in sorted(grouped.items(),key=lambda item:(item[0][1].casefold(),item[0][2])):
            a,w=totals(entries);values.append([person,label(category),money(a),money(w)])
        story.append(table(values,[51,61,33,33],(2,3)))
        for category in list(COMMISSION_LABELS)+sorted({line['category'] for line in items}-COMMISSION_LABELS.keys()):
            entries=[line for line in items if line['category']==category]
            if not entries:continue
            a,w=totals(entries)
            story.append(p(label(category)+' subtotal: '+money(a)+(' | Waiting estimate: '+money(w) if any(not line['ready'] for line in entries) else ''),'Category'))
            values=[['Manager / employee','MF file / notes','Status','Amount earned']]
            for line in sorted(entries,key=lambda line:(line['person'].casefold(),str(line['row'].get('reference')),str(line['row'].get('id')))):
                row=line['row'];meta=json.loads(row.get('source_metadata') or '{}')
                notes=[mf(row.get('reference'))]
                if meta.get('receipt_numbers'):notes.append('Receipts: '+', '.join(str(number) for number in meta['receipt_numbers']))
                if row.get('carry_forward_notice'):notes.append(row['carry_forward_notice'])
                if row.get('service_date') and period_start and str(row['service_date'])<str(period_start):notes.append('Earlier-period adjustment')
                if not line['ready'] and row.get('payment_block_reason'):notes.append(row['payment_block_reason'])
                values.append([line['person'],'\n'.join(notes),'Approved' if line['ready'] else 'Waiting',
                    'Awaiting calculation' if not line['ready'] and row.get('estimate_available') is False else money(line['amount'])])
            story.append(table(values,[51,65,25,37],(3,)))
    doc.build(story)
    return stream.getvalue()
