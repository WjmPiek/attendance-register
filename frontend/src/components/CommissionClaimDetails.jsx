const money=value=>`R ${Number(value || 0).toLocaleString('en-ZA',{minimumFractionDigits:2,maximumFractionDigits:2})}`
const metadata=row=>{try{return JSON.parse(row.source_metadata || '{}')}catch{return {}}}

export default function CommissionClaimDetails({rows,canManage,me,busy,onDownload,onHistory,onReview,onCancel}) {
  return <div className="claim-status-list">{rows.map(row=>{
    const meta=metadata(row),isActive=['pending','approved'].includes(row.status)
    return <article key={row.id} className={isActive?row.status==='approved'&&row.payment_eligible?'claim-validated':'claim-blocked':'commission-closed-claim'}>
      <h3>{`MF${String(row.reference || '').replace(/^MF[\s-]*/i,'')}`}</h3>
      {(row.fee_label||meta.fee_label)&&<p>{row.fee_label||meta.fee_label}</p>}
      <strong>{row.estimate_available===false?'Amount awaiting document checks':money(row.status==='approved'&&row.payment_eligible?row.calculated_amount:row.expected_amount ?? row.calculated_amount)}</strong>
      <p>{row.service_date}</p>
      {isActive&&row.carry_forward_notice&&<p className="commission-carry-notice" role="status">{row.carry_forward_notice}</p>}
      <p>{!isActive?row.status==='cancelled'?'Cancelled':'Rejected':!row.payment_eligible?`Document uploads or corrections required: ${row.payment_block_reason}`:row.status==='approved'?'Approved':'Documents validated — waiting to be finalised'}</p>
      <details className="commission-entry-details"><summary>Details and documents</summary>
        {(row.claim_deceased||meta.deceased)&&<p>Deceased: {row.claim_deceased||meta.deceased}</p>}
        <p>{row.commission_role==='assistant'||meta.role==='assistant'?'Assistant':'Employee'}</p>
        <p>Configured {row.commission_type==='invoice_commission'?`rate: ${row.applied_rate}%`:row.commission_type==='overtime'&&meta.calculation_type!=='fixed'?`overtime multiplier: ${row.applied_rate}×`:`fee: ${money(row.applied_rate)}`}</p>
        {row.commission_type==='invoice_commission'&&row.invoice_value_before_tax!=null&&<p>Invoice commission base: {money(row.invoice_value_before_tax)}{meta.vat_registered===true?' (excluding VAT)':meta.vat_registered===false?' (not VAT registered)':''}</p>}
        {row.notes&&<p>{row.notes}</p>}
        {!row.document_estimate&&<>
          <button type="button" className="glass-button" disabled={busy} onClick={()=>onDownload(row)}>Download claim PDF</button>
          <button type="button" className="glass-button" disabled={busy} onClick={()=>onHistory(row)}>Audit history</button>
          {canManage&&row.status==='pending'&&Number(row.employee_user_id)!==Number(me.id)&&<button type="button" className="glass-button" disabled={busy} onClick={()=>onReview(row)}>Review or correct claim</button>}
          {canManage&&!['approved','cancelled'].includes(row.status)&&<button type="button" className="danger-button" disabled={busy} onClick={()=>onCancel(row)}>Cancel claim</button>}
        </>}
        {row.document_estimate&&<p>Calculated from saved documents. Correct the source document or commission permissions to change this estimate. Included in the monthly PDF.</p>}
      </details>
    </article>
  })}</div>
}
