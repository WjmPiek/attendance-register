import { commissionLabels } from './CommissionCheckboxes'

const money=value=>`R ${Number(value || 0).toLocaleString('en-ZA',{minimumFractionDigits:2,maximumFractionDigits:2})}`

export default function BranchCommissionBreakdown({branch}) {
  return <section className="form-card"><h3>{branch.branchName}</h3>
    <p>Total: <strong>{money(branch.approved+branch.waiting)}</strong>{branch.unknown?' + items awaiting calculation':''}</p>
    <div className="staff-amounts staff-branch-amounts">
      {[['approved','Approved'],['waiting','Waiting to be finalised']].map(([status,label])=><details className={status} key={status}>
        <summary aria-label={`${branch.branchName}: ${label}`}><span>{label}</span><strong>{status==='waiting'&&branch.unknown&&branch.waiting===0?'Awaiting calculation':money(branch[status])}</strong><small>Click to view MF files</small></summary>
        <div className="staff-mf-files">
          {status==='waiting'&&branch.files[status].length>0&&<p>Amounts are estimates until finalised.</p>}
          {!branch.files[status].length&&<p>No MF files in this block.</p>}
          {branch.files[status].map(file=><details className="staff-mf-file" key={file.key}>
            <summary>{file.reference}</summary>
            <ul aria-label={`${file.reference} commissions`}>{file.items.map((item,index)=><li key={item.id ?? index}><span>{commissionLabels[item.category] || String(item.category || 'Commission').replaceAll('_',' ')}</span><span>{item.unknown?'Awaiting calculation':money(item.amount)}</span>{item.notice&&<small className="staff-commission-reason">{item.notice}</small>}</li>)}</ul>
            <p>File total: <b>{money(file.total)}</b>{file.unknown?' + items awaiting calculation':''}</p>
          </details>)}
        </div>
      </details>)}
    </div>
  </section>
}
