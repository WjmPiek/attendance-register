import { useEffect, useRef, useState } from 'react'
import { useCommissionMonth } from '../utils/useCommissionMonth'
import { getCommissionEntries, downloadCommissionForm, downloadCommissionReport, deleteCommissionEntry } from '../api/client'
import { commissionLabels } from './CommissionCheckboxes'
import { commissionGroups, commissionBranches, commissionMfFiles, readCommissionView } from '../utils/commission-groups.mjs'
import CommissionClaimDetails from './CommissionClaimDetails'
import CommissionMfDocuments from './CommissionMfDocuments'

const money=value=>`R ${Number(value || 0).toLocaleString('en-ZA',{minimumFractionDigits:2,maximumFractionDigits:2})}`
const saveBlob=(blob,name)=>{
  const url=URL.createObjectURL(blob),link=document.createElement('a')
  link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
}

export default function StaffCommissionOverview({employeeId,franchiseId,refreshKey,me,onReview,onHistory,onViewChange}) {
  const personId=employeeId || me.id
  const [month,setMonth]=useCommissionMonth(),[rows,setRows]=useState([]),[showClosed,setShowClosed]=useState(false)
  const [error,setError]=useState(''),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0)
  const [expanded,setExpanded]=useState({}),[detailKey,setDetailKey]=useState(()=>readCommissionView(window.location.search,personId).key)
  const [detailMf,setDetailMf]=useState(()=>readCommissionView(window.location.search,personId).mf)
  const [dataScope,setDataScope]=useState(''),openedDetail=useRef(false)
  const openedFile=useRef(false)
  const scope=`${personId}:${franchiseId || ''}:${month}`
  const ready=!loading&&dataScope===scope
  const canManage=me.roles.some(role=>['FranchiseUser','SuperUser'].includes(role))
  const [year,number]=month.split('-').map(Number)
  const filters={employeeUserId:personId,franchiseUserId:franchiseId,fromDate:new Date(Date.UTC(year,number-2,26)).toISOString().slice(0,10),toDate:`${month}-25`}
  useEffect(()=>{onViewChange?.(Boolean(detailKey));return()=>onViewChange?.(false)},[detailKey,onViewChange])
  useEffect(()=>{
    const sync=()=>{
      const view=readCommissionView(window.location.search,personId)
      setDetailKey(view.key)
      setDetailMf(view.mf)
      if(view.month)setMonth(view.month)
      if(!view.key)openedDetail.current=false
      if(!view.mf)openedFile.current=false
      try {if(view.key){const [branch]=JSON.parse(view.key);setExpanded(current=>({...current,[String(branch)]:true}))}} catch { /* Unknown views show no claims. */ }
    }
    sync();window.addEventListener('popstate',sync)
    return()=>window.removeEventListener('popstate',sync)
  },[personId])
  useEffect(()=>{
    let active=true
    setRows([]);setDataScope('');setLoading(true);setError('')
    const load=()=>getCommissionEntries(filters).then(data=>{
      if(active){setRows([...data.items,...(data.pending_imports||[])]);setDataScope(scope);setLoading(false);setError('')}
    }).catch(failure=>{if(active){setError(failure.message);setLoading(false)}})
    load();const timer=setInterval(load,20000)
    return()=>{active=false;clearInterval(timer)}
  },[personId,franchiseId,month,refreshKey,revision])
  const navigateDetail=(key,{replace=false,mf=''}={})=>{
    const url=new URL(window.location.href)
    for(const param of ['commission_view_group','commission_view_person','commission_view_month','commission_view_mf'])url.searchParams.delete(param)
    if(key){url.searchParams.set('commission_view_group',key);url.searchParams.set('commission_view_person',personId);url.searchParams.set('commission_view_month',month)}
    if(key&&mf)url.searchParams.set('commission_view_mf',mf)
    window.history[replace?'replaceState':'pushState']({},'',url)
    if(mf)openedFile.current=true
    else{openedFile.current=false;if(key!==detailKey)openedDetail.current=Boolean(key)}
    setDetailKey(key);setDetailMf(mf);window.scrollTo(0,0)
  }
  const back=()=>{if(openedDetail.current){openedDetail.current=false;window.history.back()}else navigateDetail('',{replace:true})}
  const backToFiles=()=>{if(openedFile.current){openedFile.current=false;window.history.back()}else navigateDetail(detailKey,{replace:true})}
  const run=async action=>{setBusy(true);setError('');try{await action()}catch(failure){setError(failure.message)}finally{setBusy(false)}}
  const groups=commissionGroups(rows,showClosed),branches=commissionBranches(groups),selected=groups.find(group=>group.key===detailKey)
  const files=commissionMfFiles(selected?.rows || []),selectedFile=files.find(file=>file.key===detailMf)
  const active=rows.filter(row=>['pending','approved'].includes(row.status))
  const approved=groups.reduce((sum,group)=>sum+group.approved,0),pending=groups.reduce((sum,group)=>sum+group.pending,0)
  const pendingCount=groups.reduce((sum,group)=>sum+group.pendingCount,0),closedCount=rows.length-active.length
  const cancel=row=>run(async()=>{if(window.confirm('Cancel this claim? Its audit history will be retained.')){await deleteCommissionEntry(row.id);setRevision(value=>value+1)}})
  const totals=(a,w,count)=><><div className="claim-validated"><span>Approved total</span><strong>{money(a)}</strong></div><div className="claim-blocked commission-awaiting-total"><span>Total awaiting document checks</span><strong>{money(w)}</strong><p>{count} item{count===1?'':'s'} waiting to be finalised.</p></div></>
  if(detailKey&&detailMf)return <section className="form-card staff-commission-overview commission-mf-page">
    <button type="button" className="glass-button" onClick={backToFiles}>← Back to MF files</button>
    <h2>{ready&&selected&&selectedFile?`${selected.branch} · ${selectedFile.reference}`:'MF file documents'}</h2>
    {error&&<p role="alert" className="error-message">{error}</p>}
    {!ready&&!error&&<p role="status">Loading MF file…</p>}
    {ready&&!error&&(selected&&selectedFile?<>
      <p>{commissionLabels[selected.category] || selected.category}</p>
      <CommissionMfDocuments branchId={selectedFile.rows[0].earning_branch_id} reference={selectedFile.key} personId={personId} category={selected.category} franchiseId={franchiseId}/>
      <details className="commission-mf-claim-details"><summary>Commission claim details</summary>
        <CommissionClaimDetails rows={selectedFile.rows} canManage={canManage} me={me} busy={busy} onReview={onReview}
          onHistory={row=>run(()=>onHistory(row))} onCancel={cancel}
          onDownload={row=>run(async()=>saveBlob(await downloadCommissionForm(row.id),`commission-${row.id}.pdf`))}/>
      </details>
    </>:<p>This MF file is not available for the selected branch and commission type.</p>)}
  </section>
  if(detailKey)return <section className="form-card staff-commission-overview commission-type-page">
    <button type="button" className="glass-button" onClick={back}>← Back to branches</button>
    <h2>{ready&&selected?`${selected.branch} · ${commissionLabels[selected.category] || selected.category}`:'Commission details'}</h2>
    <p className="muted">{filters.fromDate} to {filters.toDate}</p>
    {error&&<p role="alert" className="error-message">{error}</p>}
    {!ready&&!error&&<p role="status">Loading commissions…</p>}
    {ready&&!error&&(selected?<>
      {totals(selected.approved,selected.pending,selected.pendingCount)}
      <nav className="commission-mf-list" aria-label="MF files">{files.map(file=><button type="button" className="commission-mf-link" key={file.key} onClick={()=>navigateDetail(detailKey,{mf:file.key})}>{file.reference} →</button>)}</nav>
    </>:<p>No commissions are available for this branch and type in the selected period.</p>)}
  </section>
  return <section className="form-card staff-commission-overview">
    <h2>Monthly commissions</h2>
    <label>Commission cycle ending<input type="month" required value={month} onChange={event=>{if(event.target.value)setMonth(event.target.value)}}/></label>
    <p className="muted">{filters.fromDate} to {filters.toDate}. Late verified claims are carried forward in the finance statement.</p>
    {!ready&&!error&&<p role="status">Loading commissions…</p>}
    {error&&<p role="alert" className="error-message">{error}</p>}
    {ready&&!error&&<>
      {totals(approved,pending,pendingCount)}
      <nav className="commission-branch-list" aria-label="Commission branches">{branches.map((branch,index)=><section key={branch.key}>
        <button type="button" className="commission-branch-toggle" aria-expanded={Boolean(expanded[branch.key])} aria-controls={`commission-branch-${index}`} onClick={()=>setExpanded(current=>({...current,[branch.key]:!current[branch.key]}))}>{expanded[branch.key]?'▾':'▸'} {branch.name}</button>
        {expanded[branch.key]&&<ul id={`commission-branch-${index}`}>{branch.groups.map(group=><li key={group.key}><button type="button" className="commission-type-link" onClick={()=>navigateDetail(group.key)}>{commissionLabels[group.category] || group.category} →</button></li>)}</ul>}
      </section>)}</nav>
      {!groups.length&&<p>No commissions for the selected month.</p>}
    </>}
    <button type="button" className="glass-button" disabled={busy||!ready||!rows.length} onClick={()=>run(async()=>saveBlob(await downloadCommissionReport(filters),`commissions-${month}.pdf`))}>Download monthly PDF</button>
    {closedCount>0&&<label className="mortuary-confirm"><input type="checkbox" checked={showClosed} onChange={event=>setShowClosed(event.target.checked)}/>Show rejected and cancelled claims ({closedCount})</label>}
  </section>
}
