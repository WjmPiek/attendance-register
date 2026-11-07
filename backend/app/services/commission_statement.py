"""Monthly commission statements, with pending evidence separate from payables."""
from collections import defaultdict
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from sqlalchemy import text

from app.services.receipt_commissions import payment_eligibility, COMMISSION_LABELS


def pending_claims(db, fid, report):
    rows = db.execute(text('''SELECT c.*,u.full_name AS employee_name,b.name AS service_branch
        FROM commission_entries c JOIN users u ON u.id=c.employee_user_id
        LEFT JOIN attendance_branches b ON b.id=c.earning_branch_id
        WHERE c.franchise_user_id=:fid AND c.status IN ('pending','approved')
        AND COALESCE(c.is_cancelled,FALSE)=FALSE AND c.service_date<=:last
        AND NOT EXISTS(SELECT 1 FROM commission_monthly_report_items i WHERE i.entry_id=c.id)
        ORDER BY b.name,u.full_name,c.commission_type,c.service_date,c.id'''),
        {'fid':fid,'last':report['period_end']}).mappings().all()
    pending = []
    for row in rows:
        check = payment_eligibility(db,row)
        if row['status']=='approved' and check['payment_eligible']:
            continue
        pending.append({**dict(row), **check})
    return pending


def category_label(row):
    import json
    meta = json.loads(row.get('source_metadata') or '{}')
    label = COMMISSION_LABELS.get(row['commission_type'],row['commission_type'].replace('_',' ').title())
    if row['commission_type']=='removals' and meta.get('fee_label'):
        label += ' - '+meta['fee_label']
    return label


def statement_pdf(rows, pending, report):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    purple = colors.HexColor('#69499b')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('Cell',fontName='Helvetica',fontSize=8,leading=11,spaceAfter=0))
    styles.add(ParagraphStyle('Pending',fontName='Helvetica',fontSize=12,leading=16,textColor=colors.HexColor('#b42335'),spaceBefore=15,spaceAfter=8))
    styles.add(ParagraphStyle('Section',fontName='Helvetica',fontSize=12,leading=16,textColor=purple,spaceBefore=15,spaceAfter=8))
    def p(value,style='Cell'):
        return Paragraph(escape(str(value or '')),styles[style])
    def money(value):
        return f'R {Decimal(str(value or 0)):,.2f}'
    def table(values,widths,header=True):
        result=Table([[p(v) for v in row] for row in values],colWidths=[w*mm for w in widths],repeatRows=1 if header else 0,hAlign='LEFT')
        commands=[('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
                  ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,-1),0.3,colors.HexColor('#ded7e8'))]
        if header: commands += [('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f0ebf7'))]
        result.setStyle(TableStyle(commands));return result
    out=BytesIO()
    document=SimpleDocTemplate(out,pagesize=A4,leftMargin=17*mm,rightMargin=17*mm,topMargin=18*mm,bottomMargin=18*mm,
                               title=f"Commission statement {report['month_key']} - {report['id']}")
    story=[p("MARTIN'S FUNERALS",'Section'),p('Monthly commission statement','Title'),Spacer(1,5*mm),
           p(f"Report #{report['id']} | Holder #{report['franchise_user_id']} | {report['month_key']}"),
           p(f"Service period: {report['period_start']} to {report['period_end']} | Scheduled: {report['send_on']} SA"),
           Spacer(1,4*mm),p('Approved amounts only are for finance processing. This statement does not run payroll or transfer money. Each approved entry is reported once. Late verified claims carry forward as earlier-period adjustments.')]
    grand=Decimal(0)
    by_branch=defaultdict(list)
    for row in rows: by_branch[row.get('service_branch') or row.get('branch_name') or 'Unspecified branch'].append(row)
    for branch,items in sorted(by_branch.items()):
        story.append(p(branch+' - APPROVED','Section'))
        grouped=defaultdict(lambda:[0,Decimal(0)])
        for row in items:
            key=(row['employee_name'],category_label(row))
            grouped[key][0]+=1;grouped[key][1]+=Decimal(str(row['calculated_amount']))
        values=[['Manager / employee','Commission category','Items','Approved amount']]
        values += [[name,category,str(count),money(total)] for (name,category),(count,total) in sorted(grouped.items())]
        total=sum((Decimal(str(r['calculated_amount'])) for r in items),Decimal(0));grand+=total
        story += [table(values,[52,74,15,35]),Spacer(1,3*mm),p('Branch approved total: '+money(total))]
    story += [Spacer(1,5*mm),p('TOTAL APPROVED FOR FINANCE: '+money(grand),'Section')]
    if not rows: story.append(p('No newly reportable approved commissions.'))
    if rows:
        people={}
        for row in rows:
            key=row.get('employee_user_id',row['employee_name'])
            person=people.setdefault(key,{'name':row['employee_name'],'total':Decimal(0)})
            person['total']+=Decimal(str(row['calculated_amount']))
        story += [p('Approved totals by manager / employee - all service branches','Section'),
                  table([['Manager / employee','Approved total']]+[[person['name'],money(person['total'])] for person in sorted(people.values(),key=lambda item:item['name'])],[126,50])]
        story.append(p('Approved claim details','Section'))
        values=[['Claim / date','Branch / person','Category / MF file','Amount']]
        for row in rows:
            earlier=' | Earlier-period adjustment' if str(row['service_date'])<str(report['period_start']) else ''
            if row.get('carry_forward_notice'): earlier += ' | '+row['carry_forward_notice']
            values.append([f"#{row['id']} | {row['service_date']}{earlier}",f"{row.get('service_branch') or row.get('branch_name') or ''} | {row['employee_name']}",f"{category_label(row)} | MF {row['reference']}",money(row['calculated_amount'])])
        story.append(table(values,[38,55,53,30]))
    if pending: story.append(PageBreak())
    story += [p('PENDING - NOT APPROVED FOR PAYMENT','Pending'),p('These estimates are excluded from the approved total. Missing documents, unmatched details and unpaid invoices remain blocked.')]
    if pending:
        values=[['Branch / person','Category / MF file','Estimate','Required action']]
        for row in pending:
            reason=row.get('payment_block_reason') or 'Awaiting automatic validation'
            if row.get('carry_forward_notice'): reason += ' '+row['carry_forward_notice']
            values.append([f"{row.get('service_branch') or row.get('branch_name') or ''} | {row['employee_name']}",f"{category_label(row)} | MF {row['reference']}",'Awaiting documents' if row.get('estimate_available') is False else money(row.get('expected_amount',row['calculated_amount'])),reason])
        story.append(table(values,[47,47,27,55]))
    else: story.append(p('No pending claims for this cutoff.'))
    story += [Spacer(1,5*mm),p(f"Use report #{report['id']} as the unique finance processing reference. Do not process the same report twice.")]
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.setFillColor(purple)
        canvas.drawString(17*mm,10*mm,f"Commission statement #{report['id']} - {report['month_key']}")
        canvas.drawRightString(193*mm,10*mm,f'Page {doc.page}')
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()
