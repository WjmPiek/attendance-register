import { useEffect, useState } from 'react'
import { apiRequest, apiBlob } from '../api/client'
import MonthlyCommissionStatement from './MonthlyCommissionStatement'
import CommissionCheckboxes, { commissionLabels } from './CommissionCheckboxes'

const currentMonth = () => new Date(Date.now() + 7200000).toISOString().slice(0,7)
export default function BranchCommissionHub({ franchiseId, branchId = '', onBranchChange }) {
  const [data,setData]=useState(null),[error,setError]=useState(''),[month,setMonth]=useState(currentMonth)
  const [selected,setSelected]=useState(null),[editor,setEditor]=useState(null),[busy,setBusy]=useState(false)
  const activeBranch=String(branchId || '')
  const setActiveBranch=value=>onBranchChange?.(value)
  const suffix=franchiseId?`?franchise_user_id=${franchiseId}`:''
  const load=async()=>setData(await apiRequest(`/receipt-commissions/settings${suffix}`))
  useEffect(()=>{load().catch(e=>setError(e.message))},[suffix])
  const enabled=(e,bid)=>e.commission_branches?.[String(bid)]?.enabled_types||[]
  const members=branch=>data.employees.filter(e=>e.branch_id===branch.id||enabled(e,branch.id).length)
  const download=async(branch,employee)=>{
    try { const query=new URLSearchParams({month,...(franchiseId?{franchise_user_id:franchiseId}:{}),...(branch?{branch_id:branch}:{}),...(employee?{employee_user_id:employee}:{})})
      const blob=await apiBlob(`/receipt-commissions/report.pdf?${query}`),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`commissions-${month}.pdf`;link.click();URL.revokeObjectURL(url)
    }catch(e){setError(e.message)}
  }
  const openEditor=async(employee,branch)=>{
    try {const preferences=await apiRequest(`/receipt-commissions/options/${employee.user_id}`);setEditor({employee,branch,preferences,values:preferences.commission_branches||{}});setError('')}
    catch(e){setError(e.message)}
  }
  const save=async()=>{
    setBusy(true);try {await apiRequest('/receipt-commissions/options',{method:'PUT',body:JSON.stringify({employee_user_id:editor.employee.user_id,franchise_user_id:data.franchise_user_id,commission_branches:editor.values,receipt_percentage:editor.preferences.options.invoice_commission?.rate??null})});setEditor(null);await load();setError('')}
    catch(e){setError(e.message)}finally{setBusy(false)}
  }
  return <section className="mortuary-book"><div className="form-card"><h2>All branches · Staff and commissions</h2><p>Each linked branch has its own employee and manager commission permissions. Statements and PDFs show only commissions earned for the selected branch.</p><div className="mortuary-rates"><label>Branch view<select value={activeBranch} onChange={e=>{setActiveBranch(e.target.value);setSelected(null);setEditor(null)}}><option value="">All linked branches</option>{data?.branches.map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select></label><label>Report month<input type="month" value={month} onChange={e=>setMonth(e.target.value)}/></label></div><button type="button" className="glass-button" onClick={()=>download(activeBranch)}>Download {activeBranch?'selected branch':'all branches'} PDF</button>{error&&<p role="alert" className="error-message">{error}</p>}</div>
    {data?.branches.filter(b=>!activeBranch||String(b.id)===activeBranch).map(branch=><section className="form-card" key={branch.id}><div className="section-heading"><h3>{branch.name}</h3><div className="button-row">{!activeBranch&&<button type="button" className="glass-button" onClick={()=>{setActiveBranch(String(branch.id));setSelected(null)}}>Open this branch</button>}<button type="button" onClick={()=>download(branch.id)}>Branch commission PDF</button></div></div>{members(branch).map(e=><div className="branch-staff-row" key={e.user_id}><div><strong>{e.full_name} · {e.employee_role}</strong><small className="commission-branch-summary">Home branch: {e.branch_name}<br/>Enabled here: {enabled(e,branch.id).map(c=>commissionLabels[c]).join(', ')||'No commissions enabled'}</small></div><button type="button" className="glass-button" onClick={()=>openEditor(e,branch)}>Commission permissions</button><button type="button" className="glass-button" onClick={()=>setSelected({employee:e,branch})}>Monthly commissions</button><button type="button" className="glass-button" onClick={()=>download(branch.id,e.user_id)}>Employee PDF</button></div>)}{!members(branch).length&&<p>No active staff are assigned to or enabled for commissions at this branch.</p>}</section>)}
    {editor&&<section className="form-card"><h3>{editor.employee.full_name} · {editor.branch.name}</h3><CommissionCheckboxes branches={[editor.branch]} branchOptions={editor.values} onBranchOptionsChange={values=>setEditor(v=>({...v,values}))}/><div className="button-row"><button type="button" disabled={busy} onClick={save}>Save this branch’s commission permissions</button><button type="button" className="glass-button" disabled={busy} onClick={()=>setEditor(null)}>Cancel</button></div></section>}
    {selected&&<section className="form-card"><button type="button" className="glass-button" onClick={()=>setSelected(null)}>Close employee statement</button><h3>{selected.employee.full_name} · {selected.branch.name}</h3><MonthlyCommissionStatement employeeUserId={selected.employee.user_id} franchiseId={franchiseId} earningBranchId={selected.branch.id}/></section>}
  </section>
}
