import { useEffect, useRef, useState } from 'react'
import { apiRequest, apiBlob } from '../api/client'
import './MortuaryBook.css'

const labels={mortuary:'Mortuary Book',invoice:'Invoice',receipt:'Receipt'}
const money=value=>value==null?'Not uploaded':`R ${Number(value).toLocaleString('en-ZA',{minimumFractionDigits:2,maximumFractionDigits:2})}`
const timestamp=value=>value?new Date(/[zZ]|\+\d\d:\d\d$/.test(value)?value:value+'Z').toLocaleString('en-ZA',{timeZone:'Africa/Johannesburg'}):'—'

export default function CommissionDocumentRegister({franchiseId,onBack}) {
  const [month,setMonth]=useState(new Date(Date.now()+7200000).toISOString().slice(0,7))
  const [branch,setBranch]=useState(''),[deleted,setDeleted]=useState(false),[offset,setOffset]=useState(0)
  const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('')
  const [selected,setSelected]=useState(null),[pdf,setPdf]=useState(''),[correction,setCorrection]=useState(null),[reason,setReason]=useState('')
  const [log,setLog]=useState(null),[logOffset,setLogOffset]=useState(0)
  const correctionRef=useRef(null)
  useEffect(()=>{if(data&&branch&&!data.branches.some(b=>String(b.id)===branch)){setBranch('');setOffset(0)}},[data,branch])
  useEffect(()=>{if(correction)correctionRef.current?.scrollIntoView({block:'start',behavior:'smooth'})},[correction])
  const scope=franchiseId?{franchise_user_id:franchiseId}:{}
  const query=values=>new URLSearchParams({...scope,...values})
  const load=async()=>{const result=await apiRequest(`/commission-documents?${query({month,include_deleted:deleted,offset,...(branch?{branch_id:branch}:{})})}`);setData(result)}
  useEffect(()=>{let active=true;setData(null);setError('');apiRequest(`/commission-documents?${query({month,include_deleted:deleted,offset,...(branch?{branch_id:branch}:{})})}`).then(d=>{if(active)setData(d)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[month,branch,deleted,offset,franchiseId])
  useEffect(()=>()=>{if(pdf)URL.revokeObjectURL(pdf)},[pdf])
  const run=async fn=>{setBusy(true);setError('');try{await fn()}catch(e){setError(e.message)}finally{setBusy(false)}}
  const view=id=>run(async()=>{
    const doc=await apiRequest(`/commission-documents/${id}?${query({})}`)
    setSelected(doc);setPdf('');setLog(null)
    if(doc.original_available){const blob=await apiBlob(`/commission-documents/${id}/file?${query({})}`);setPdf(URL.createObjectURL(blob))}
  })
  const download=id=>run(async()=>{const blob=await apiBlob(`/commission-documents/${id}/file?${query({download:true})}`),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`commission-document-${id}.pdf`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)})
  const history=(page=0)=>run(async()=>{const result=await apiRequest(`/commission-documents/activity?${query({offset:page,...(selected?{document_id:selected.id}:{})})}`);setLog(result);setLogOffset(page)})
  const correct=()=>run(async()=>{
    const action=correction.deleted_at?'restore':'archive'
    const result=await apiRequest(`/commission-documents/${correction.id}/${action}`,{method:'POST',body:JSON.stringify({...scope,reason})})
    setNotice(result.message||'Document restored.');setCorrection(null);setReason('');setSelected(null);setPdf('');await load()
  })
  return <section className="mortuary-book commission-document-register">
    <header className="form-card"><div className="button-row">{selected?<button type="button" className="glass-button" onClick={()=>{setSelected(null);setPdf('');setLog(null)}}>← Monthly documents</button>:onBack&&<button type="button" className="glass-button" onClick={onBack}>← Back</button>}</div>
      <h1>Commission documents</h1><p>View Mortuary Books, invoices and every payment receipt under their printed service branch. Payment checks include matching evidence from other months.</p>
      <p>Deleting an incorrect upload removes it from active commission evidence. Its original and audit history are retained, and it can be restored. Cases with approved commissions require Head Office review first.</p>
    </header>
    {error&&<p role="alert" className="error-message">{error}</p>}{notice&&<p role="status" className="success-message">{notice}</p>}
    {selected?<section className="form-card"><h2>{labels[selected.kind]} · MF {selected.record.reference}</h2><p>{selected.record.branch} · {selected.record.deceased}</p><p>Uploaded {timestamp(selected.created_at)} · {selected.deleted_at?'Deleted from active evidence':'Active evidence'}</p>
      <dl className="document-field-list">{Object.entries(selected.record).filter(([key])=>!['source_hash','external_branch_id','earning_branch_id'].includes(key)).map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{typeof value==='object'?JSON.stringify(value):String(value??'—')}</dd></div>)}</dl>
      <h3>Allocated employees and managers</h3>{selected.staff.map(p=><p key={p.employee_user_id}>{p.full_name} · {p.removal_role||'Receipt commission recipient'}</p>)}{!selected.staff.length&&<p>No employee allocations on this document.</p>}
      <div className="button-row">{selected.original_available&&<button type="button" disabled={busy} onClick={()=>download(selected.id)}>Download original PDF</button>}<button type="button" className="glass-button" disabled={busy} onClick={()=>history()}>Document audit history</button><button type="button" className="glass-button" disabled={busy} onClick={()=>{setCorrection(selected);setReason('')}}>{selected.deleted_at?'Restore document':'Delete incorrect upload'}</button></div>
      {pdf?<iframe className="commission-document-pdf" src={pdf} title={`Original ${labels[selected.kind]} ${selected.id}`}/>:!selected.original_available&&<p>This older upload did not retain its original PDF. The extracted details are shown above.</p>}
    </section>:<>
      <section className="form-card"><div className="mortuary-rates"><label>Upload month (South Africa)<input type="month" value={month} onChange={e=>{if(e.target.value){setMonth(e.target.value);setOffset(0)}}}/></label><label>Branch<select value={branch} onChange={e=>{setBranch(e.target.value);setOffset(0)}}><option value="">All linked branches</option>{data?.branches.map(b=><option key={b.id} value={b.id}>{b.name}{b.is_active?'':' · inactive'}</option>)}</select></label></div>
        <label className="mortuary-confirm"><input type="checkbox" checked={deleted} onChange={e=>{setDeleted(e.target.checked);setOffset(0)}}/>Include deleted uploads</label><button type="button" className="glass-button" disabled={busy} onClick={()=>history()}>View activity log</button>
        {!data&&!error&&<p role="status">Loading document register…</p>}{data&&<p>{data.total} document{data.total===1?'':'s'} uploaded in this month.</p>}
      </section>
      {data?.branches.filter(b=>(!branch||String(b.id)===branch)&&data.cases.some(c=>c.branch_id===b.id)).map(b=>{const cases=data.cases.filter(c=>c.branch_id===b.id);return <section className="form-card" key={b.id}><h2>{b.name} · {month}</h2>{cases.map(c=><article className="mortuary-record" key={c.mf}><h3>MF {c.mf} · {c.deceased||'Deceased not recorded'}</h3><div className="document-payment-summary"><p>Invoice total<strong>{money(c.invoice_total)}</strong></p><p>All receipts to date<strong>{money(c.total_received)}</strong></p><p>Balance<strong>{money(c.balance)}</strong></p></div><p className={c.ready?'success-message':'claim-blocked'}>{c.reason}</p><div className="table-wrap"><table><thead><tr><th>Document</th><th>Number / service date</th><th>Amount</th><th>Uploaded</th><th>Status</th><th>Actions</th></tr></thead><tbody>{data.documents.filter(d=>c.document_ids.includes(d.id)).map(d=><tr key={d.id}><td>{labels[d.kind]}</td><td>{d.kind==='receipt'?d.record.receipt_number:d.kind==='invoice'?d.record.invoice_number:d.record.reference}<br/>{d.record.service_date}</td><td>{d.kind==='mortuary'?'—':money(d.record.invoice_total??d.record.gross_received)}</td><td>{timestamp(d.created_at)}</td><td>{d.deleted_at?'Deleted':'Active'}</td><td><div className="button-row"><button type="button" className="glass-button" disabled={busy} onClick={()=>view(d.id)}>View</button><button type="button" className="glass-button" disabled={busy} onClick={()=>{setCorrection(d);setReason('')}}>{d.deleted_at?'Restore':'Delete'}</button></div></td></tr>)}</tbody></table></div></article>)}</section>})}
      {data&&data.total>data.limit&&<div className="button-row"><button type="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-data.limit))}>Previous documents</button><span>{offset+1}–{Math.min(offset+data.limit,data.total)} of {data.total}</span><button type="button" disabled={offset+data.limit>=data.total} onClick={()=>setOffset(offset+data.limit)}>Next documents</button></div>}
    </>}
    {correction&&<form ref={correctionRef} className="form-card" onSubmit={e=>{e.preventDefault();correct()}}><h2>{correction.deleted_at?'Restore document':'Delete incorrect upload'} #{correction.id}</h2><p>{correction.record.branch} · MF {correction.record.reference} · {labels[correction.kind]}</p><label>Reason (recorded in the audit log)<textarea required minLength={3} maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)}/></label><div className="button-row"><button type="submit" disabled={busy||reason.trim().length<3}>{busy?'Saving…':correction.deleted_at?'Restore document':'Confirm deletion'}</button><button type="button" className="glass-button" disabled={busy} onClick={()=>setCorrection(null)}>Cancel</button></div></form>}
    {log&&<section className="form-card"><h2>{selected?'Document audit history':'Document activity log'}</h2><button type="button" className="glass-button" onClick={()=>setLog(null)}>Close log</button><div className="table-wrap"><table><thead><tr><th>Date (South Africa)</th><th>Person</th><th>Action / document</th><th>Details</th></tr></thead><tbody>{log.items.map(item=><tr key={item.id}><td>{timestamp(item.created_at)}</td><td>{item.actor_name||`User ${item.actor_user_id}`}</td><td>{item.action.replaceAll('_',' ')}<br/>#{item.entity_id||'—'}</td><td>{item.note}<details><summary>Recorded changes</summary><pre>{JSON.stringify({before:item.old_values?JSON.parse(item.old_values):null,after:item.new_values?JSON.parse(item.new_values):null},null,2)}</pre></details></td></tr>)}</tbody></table></div>{!log.items.length&&<p>No activity recorded.</p>}<div className="button-row"><button type="button" disabled={busy||!logOffset} onClick={()=>history(Math.max(0,logOffset-200))}>Previous activity</button><button type="button" disabled={busy||!log.has_more} onClick={()=>history(logOffset+200)}>Next activity</button></div></section>}
  </section>
}
