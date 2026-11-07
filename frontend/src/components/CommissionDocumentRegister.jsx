import { useEffect, useRef, useState } from 'react'
import { apiRequest, apiBlob } from '../api/client'
import './MortuaryBook.css'
import CommissionEvidenceImport from './CommissionEvidenceImport'

const labels={mortuary:'Mortuary Book',invoice:'Invoice',receipt:'Receipt'}
const money=value=>value==null?'Not uploaded':`R ${Number(value).toLocaleString('en-ZA',{minimumFractionDigits:2,maximumFractionDigits:2})}`
const timestamp=value=>value?new Date(/[zZ]|\+\d\d:\d\d$/.test(value)?value:value+'Z').toLocaleString('en-ZA',{timeZone:'Africa/Johannesburg'}):'—'

export default function CommissionDocumentRegister({franchiseId,onBack}) {
  const [month,setMonth]=useState(new Date(Date.now()+7200000).toISOString().slice(0,7))
  const [branch,setBranch]=useState(''),[deleted,setDeleted]=useState(false),[offset,setOffset]=useState(0)
  const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('')
  const [selected,setSelected]=useState(null),[pdf,setPdf]=useState(''),[correction,setCorrection]=useState(null),[reason,setReason]=useState('')
  const [openedCase,setOpenedCase]=useState(null),[uploadKind,setUploadKind]=useState('')
  const detailRef=useRef(null)
  const [log,setLog]=useState(null),[logOffset,setLogOffset]=useState(0)
  const correctionRef=useRef(null)
  useEffect(()=>{if(openedCase||selected||uploadKind){detailRef.current?.scrollIntoView({block:'start',behavior:'smooth'});detailRef.current?.focus({preventScroll:true})}},[openedCase,selected,uploadKind])
  useEffect(()=>{setOpenedCase(null);setSelected(null);setPdf('');setLog(null);setUploadKind('')},[franchiseId])
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
  const fetchCase=async (branchId,mf)=>{const result=await apiRequest(`/commission-documents/case?${query({branch_id:branchId,mf,include_deleted:deleted})}`);setOpenedCase(result)}
  const openCase=c=>run(async()=>{await fetchCase(c.branch_id,c.mf);setSelected(null);setPdf('');setLog(null)})
  const download=id=>run(async()=>{const blob=await apiBlob(`/commission-documents/${id}/file?${query({download:true})}`),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`commission-document-${id}.pdf`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)})
  const history=(page=0)=>run(async()=>{const result=await apiRequest(`/commission-documents/activity?${query({offset:page,...(selected?{document_id:selected.id}:{})})}`);setLog(result);setLogOffset(page)})
  const correct=()=>run(async()=>{
    const action=correction.deleted_at?'restore':'archive'
    const result=await apiRequest(`/commission-documents/${correction.id}/${action}`,{method:'POST',body:JSON.stringify({...scope,reason})})
    setNotice(result.message||'Document restored.');setCorrection(null);setReason('');setSelected(null);setPdf('');await load();if(openedCase)await fetchCase(openedCase.case.branch_id,openedCase.case.mf)
  })
  return <section className="mortuary-book commission-document-register">
    <header className="form-card"><div className="button-row">{selected?<button type="button" className="glass-button" onClick={()=>{setSelected(null);setPdf('');setLog(null)}}>← {openedCase?'MF File documents':'Monthly documents'}</button>:openedCase?<button type="button" className="glass-button" onClick={()=>{setOpenedCase(null);setLog(null);setUploadKind('')}}>← All MF Files</button>:onBack&&<button type="button" className="glass-button" onClick={onBack}>← Back</button>}</div>
      <h1>Commission documents</h1><p>View Mortuary Books, invoices and every payment receipt under their printed service branch. Payment checks include matching evidence from other months.</p>
      <p>Deleting an incorrect upload removes it from active commission evidence. Its original and audit history are retained, and it can be restored. Cases with approved commissions require Head Office review first.</p>
    </header>
    {error&&<p role="alert" className="error-message">{error}</p>}{notice&&<p role="status" className="success-message">{notice}</p>}
    {uploadKind?<section ref={detailRef} tabIndex={-1} className="form-card"><button type="button" className="glass-button" onClick={()=>run(async()=>{setUploadKind('');await load();if(openedCase)await fetchCase(openedCase.case.branch_id,openedCase.case.mf)})}>← Recheck MF File documents</button><CommissionEvidenceImport kind={uploadKind} franchiseId={franchiseId}/></section>:selected?<section ref={detailRef} tabIndex={-1} className="form-card"><h2>{labels[selected.kind]} · MF {selected.record.reference}</h2><p>{selected.record.branch} · {selected.record.deceased}</p><p>Uploaded {timestamp(selected.created_at)} · {selected.deleted_at?'Deleted from active evidence':'Active evidence'}</p>
      <dl className="document-field-list">{Object.entries(selected.record).filter(([key])=>!['source_hash','external_branch_id','earning_branch_id'].includes(key)).map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{typeof value==='object'?JSON.stringify(value):String(value??'—')}</dd></div>)}</dl>
      <h3>Allocated employees and managers</h3>{selected.staff.map(p=><p key={p.employee_user_id}>{p.full_name} · {p.removal_role||'Receipt commission recipient'}</p>)}{!selected.staff.length&&<p>Commission recipients are determined by staff claims; uploads do not assign recipients.</p>}
      <div className="button-row">{selected.original_available&&<button type="button" disabled={busy} onClick={()=>download(selected.id)}>Download original PDF</button>}<button type="button" className="glass-button" disabled={busy} onClick={()=>history()}>Document audit history</button><button type="button" className="glass-button" disabled={busy} onClick={()=>{setCorrection(selected);setReason('')}}>{selected.deleted_at?'Restore document':'Delete incorrect upload'}</button></div>
      {pdf?<iframe className="commission-document-pdf" src={pdf} title={`Original ${labels[selected.kind]} ${selected.id}`}/>:!selected.original_available&&<p>This older upload did not retain its original PDF. The extracted details are shown above.</p>}
    </section>:openedCase?<section ref={detailRef} tabIndex={-1} className="form-card">
      <h2>{openedCase.case.branch} · MF {openedCase.case.reference || openedCase.case.mf}</h2><p>{openedCase.case.deceased}</p>
      <p className={openedCase.case.ready?'commission-file-status complete':'commission-file-status incomplete'}>{openedCase.case.ready?'Complete':'Not Complete'}</p>
      {!openedCase.case.ready&&<section className="commission-case-issues" aria-label="Items to fix"><h3>Items to fix</h3>{(openedCase.case.issues||[{action:'inspect',label:'Check the documents below',message:openedCase.case.reason,document_ids:openedCase.documents.map(d=>d.id)}]).map((issue,index)=><article key={index}><h4>{issue.label}</h4><p>{issue.message}</p>{issue.action==='upload'&&<button type="button" disabled={busy} onClick={()=>setUploadKind(issue.kind)}>{issue.label} →</button>}{issue.action==='main_vat'&&<p>Correct the branch VAT number in the main system, then reopen Attendance to sync it. A blank synced VAT number means no VAT deduction.</p>}{issue.document_ids?.map(id=>{const doc=openedCase.documents.find(d=>d.id===id);return doc&&<button type="button" className="glass-button" key={id} disabled={busy} onClick={()=>view(id)}>Check {labels[doc.kind]} {doc.record.receipt_number||doc.record.invoice_number||doc.record.reference} →</button>})}</article>)}</section>}
      <p>{openedCase.case.reason}</p><p className="muted">All documents for this branch and MF File, across every upload month.</p>
      <div className="document-payment-summary"><p>Invoice total<strong>{money(openedCase.case.invoice_total)}</strong></p><p>All receipts<strong>{money(openedCase.case.total_received)}</strong></p><p>Balance<strong>{money(openedCase.case.balance)}</strong></p></div>
      <div className="table-wrap"><table><thead><tr><th>Document</th><th>Number / service date</th><th>Amount</th><th>Uploaded</th><th>Status</th><th>Open</th></tr></thead><tbody>{openedCase.documents.map(d=><tr key={d.id}>
        <td>{labels[d.kind]}</td><td>{d.kind==='receipt'?d.record.receipt_number:d.kind==='invoice'?d.record.invoice_number:d.record.reference}<br/>{d.record.service_date}</td>
        <td>{d.kind==='mortuary'?'—':money(d.record.invoice_total??d.record.gross_received)}</td><td>{timestamp(d.created_at)}</td><td>{d.deleted_at?'Deleted':'Active'}</td>
        <td><div className="button-row"><button type="button" className="glass-button" disabled={busy} onClick={()=>view(d.id)}>View document</button>{d.original_available&&<button type="button" className="glass-button" disabled={busy} onClick={()=>download(d.id)}>Download PDF</button>}<button type="button" className="glass-button" disabled={busy} onClick={()=>{setCorrection(d);setReason('')}}>{d.deleted_at?'Restore':'Delete incorrect upload'}</button></div></td>
      </tr>)}</tbody></table></div>{!openedCase.documents.length&&<p>No active documents remain. Use Include deleted uploads in the register to view archived evidence.</p>}
    </section>:<>
      <section className="form-card"><div className="mortuary-rates"><label>Upload month (South Africa)<input type="month" value={month} onChange={e=>{if(e.target.value){setMonth(e.target.value);setOffset(0)}}}/></label><label>Branch<select value={branch} onChange={e=>{setBranch(e.target.value);setOffset(0)}}><option value="">All branches</option>{data?.branches.map(b=><option key={b.id} value={b.id}>{b.name}{b.is_active?'':' · inactive'}</option>)}</select></label></div>
        <label className="mortuary-confirm"><input type="checkbox" checked={deleted} onChange={e=>{setDeleted(e.target.checked);setOffset(0)}}/>Include deleted uploads</label><button type="button" className="glass-button" disabled={busy} onClick={()=>history()}>View activity log</button>
        {!data&&!error&&<p role="status">Loading document register…</p>}{data&&<p>{data.total} document{data.total===1?'':'s'} uploaded in this month.</p>}
      </section>
      {data?.branches.filter(b=>(!branch||String(b.id)===branch)&&data.cases.some(c=>c.branch_id===b.id)).map(b=><section className="form-card" key={b.id}>
        <h2>{b.name}</h2><div className="commission-case-grid">{data.cases.filter(c=>c.branch_id===b.id).map(c=><button type="button" className="commission-case-card" key={c.mf} disabled={busy} onClick={()=>openCase(c)}>
          <span className="commission-case-title">MF {c.reference || c.mf}</span><span>{c.deceased||'Deceased not recorded'}</span>
          <span className={c.ready?'commission-file-status complete':'commission-file-status incomplete'}>{c.ready?'Complete':'Not Complete'}</span>
          <span>Mortuary Book: {c.document_counts?.mortuary||0} · Invoice: {c.document_counts?.invoice||0} · Receipts: {c.document_counts?.receipt||0}</span>
          <span>{c.reason}</span><span className="commission-case-link">Open MF File documents →</span>
        </button>)}</div></section>)}
      {data&&data.case_total>data.limit&&<div className="button-row"><button type="button" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-data.limit))}>Previous MF Files</button><span>{offset+1}–{Math.min(offset+data.limit,data.case_total)} of {data.case_total} MF Files</span><button type="button" disabled={offset+data.limit>=data.case_total} onClick={()=>setOffset(offset+data.limit)}>Next MF Files</button></div>}
    </>}
    {correction&&<form ref={correctionRef} className="form-card" onSubmit={e=>{e.preventDefault();correct()}}><h2>{correction.deleted_at?'Restore document':'Delete incorrect upload'} #{correction.id}</h2><p>{correction.record.branch} · MF {correction.record.reference} · {labels[correction.kind]}</p><label>Reason (recorded in the audit log)<textarea required minLength={3} maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)}/></label><div className="button-row"><button type="submit" disabled={busy||reason.trim().length<3}>{busy?'Saving…':correction.deleted_at?'Restore document':'Confirm deletion'}</button><button type="button" className="glass-button" disabled={busy} onClick={()=>setCorrection(null)}>Cancel</button></div></form>}
    {log&&<section className="form-card"><h2>{selected?'Document audit history':'Document activity log'}</h2><button type="button" className="glass-button" onClick={()=>setLog(null)}>Close log</button><div className="table-wrap"><table><thead><tr><th>Date (South Africa)</th><th>Person</th><th>Action / document</th><th>Details</th></tr></thead><tbody>{log.items.map(item=><tr key={item.id}><td>{timestamp(item.created_at)}</td><td>{item.actor_name||`User ${item.actor_user_id}`}</td><td>{item.action.replaceAll('_',' ')}<br/>#{item.entity_id||'—'}</td><td>{item.note}<details><summary>Recorded changes</summary><pre>{JSON.stringify({before:item.old_values?JSON.parse(item.old_values):null,after:item.new_values?JSON.parse(item.new_values):null},null,2)}</pre></details></td></tr>)}</tbody></table></div>{!log.items.length&&<p>No activity recorded.</p>}<div className="button-row"><button type="button" disabled={busy||!logOffset} onClick={()=>history(Math.max(0,logOffset-200))}>Previous activity</button><button type="button" disabled={busy||!log.has_more} onClick={()=>history(logOffset+200)}>Next activity</button></div></section>}
  </section>
}

