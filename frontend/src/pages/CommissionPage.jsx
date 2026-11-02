import ServiceClaimPanel from '../components/ServiceClaimPanel'
import StaffCommissionOverview from '../components/StaffCommissionOverview'
import { useEffect, useMemo, useState } from 'react'
import { downloadCommissionForm, getCommissionEmployees, reviewCommissionEntry,
  getFranchiseUsers, getCommissionEntryHistory, getCommissionEntry } from '../api/client'

export default function CommissionPage({ me }) {
  const isEmployee = me.roles.includes('EmployeeUser')
  const isManager = me.roles.includes('ManagerUser')
  const isSelfSubmitter = isEmployee || isManager
  const isFranchise = me.roles.includes('FranchiseUser')
  const isSuper = me.roles.includes('SuperUser')
  const isFranchiseScope = isFranchise || isSuper
  const canReview = me.roles.some(r => ['FranchiseUser','SuperUser'].includes(r))
  const [employees,setEmployees]=useState([])
  const [franchises,setFranchises]=useState([]), [selectedFranchise,setSelectedFranchise]=useState(null)
  const [overviewKey, setOverviewKey] = useState(0)
  const [editing,setEditing]=useState(null)
  const [selectedEmployee,setSelectedEmployee]=useState(null)
  const [employeeSearch,setEmployeeSearch]=useState('')
  const [error,setError]=useState(''), [notice,setNotice]=useState(''), [loading,setLoading]=useState(true)
  const [history,setHistory]=useState(null)
  const [reviewPdfUrl,setReviewPdfUrl]=useState('')

  const refresh=async()=>{ setOverviewKey(value => value + 1) }
  const load=async()=>{
    setLoading(true)
    try {
      if (isSuper) setFranchises((await getFranchiseUsers()).filter(x=>x.is_active!==false&&x.login_active!==false))
      else setEmployees(await getCommissionEmployees())
    } catch (e) { setError(e.message || 'Staff could not load.') }
    finally { setLoading(false) }
  }
  useEffect(()=>{load()},[])
  useEffect(()=>()=>{if(reviewPdfUrl)URL.revokeObjectURL(reviewPdfUrl)},[reviewPdfUrl])

  const linkedEmployees=useMemo(()=>employees.filter(x=>x.staff_type==='employee'),[employees])
  const staffHierarchy=useMemo(()=>{
    const q=employeeSearch.trim().toLowerCase()
    const matches=item=>[item.full_name,item.employee_number,item.employee_role,item.email,item.office_address_assigned].some(v=>String(v||'').toLowerCase().includes(q))
    const managers=employees.filter(item=>item.staff_type==='manager')
    const assignedIds=new Set()
    const groups=managers.map(manager=>{
      const children=employees.filter(item=>item.staff_type==='employee'&&Number(item.manager_user_id)===Number(manager.manager_profile_id))
      children.forEach(item=>assignedIds.add(Number(item.user_id)))
      const visibleChildren=q?children.filter(matches):children
      if(q&&!matches(manager)&&!visibleChildren.length)return null
      return {manager,employees:visibleChildren}
    }).filter(Boolean)
    const direct=employees.filter(item=>item.staff_type==='employee'&&!assignedIds.has(Number(item.user_id))&&(!q||matches(item)))
    return {groups,direct}
  },[employees,employeeSearch])
  const payload=(x)=>({...x,earning_branch_id:x.earning_branch_id?Number(x.earning_branch_id):null,employee_user_id:x.employee_user_id?Number(x.employee_user_id):null,quantity:Number(x.quantity||1),invoice_value_before_tax:x.invoice_value_before_tax===''?null:Number(x.invoice_value_before_tax),hours:x.hours===''?null:Number(x.hours),hourly_rate:x.hourly_rate===''?null:Number(x.hourly_rate)})
  const closeReview=()=>{setEditing(null);if(reviewPdfUrl)URL.revokeObjectURL(reviewPdfUrl);setReviewPdfUrl('')}
  const openReview=async entry=>{
    try{
      setError('');setLoading(true)
      const blob=await downloadCommissionForm(entry.id)
      if(reviewPdfUrl)URL.revokeObjectURL(reviewPdfUrl)
      setReviewPdfUrl(URL.createObjectURL(blob));setEditing({...entry})
    }catch(x){setError(x.message||'Commission review document could not load.')}finally{setLoading(false)}
  }
  const review=async status=>{try{await reviewCommissionEntry(editing.id,{...payload(editing),status,review_notes:editing.review_notes||''});closeReview();setNotice(`Commission ${status}. Employee notification sent.`);await refresh()}catch(x){setError(x.message)}}
  const openEmployee=async employee=>{
    setSelectedEmployee(employee);setEditing(null);setHistory(null);setNotice('');setError('')
    const url=new URL(window.location.href);url.searchParams.set('commission_employee',String(employee.user_id));window.history.replaceState({},'',url)
  }
  const closeEmployee=()=>{
    setSelectedEmployee(null);setEditing(null);setHistory(null)
    const url=new URL(window.location.href);url.searchParams.delete('commission_employee');window.history.replaceState({},'',url)
  }

  useEffect(()=>{
    if(!isFranchiseScope || !employees.length || selectedEmployee)return
    const id=Number(new URLSearchParams(window.location.search).get('commission_employee')||0)
    const employee=employees.find(x=>Number(x.user_id)===id)
    if(employee)openEmployee(employee)
  },[employees,isFranchiseScope])

  const openFranchise=async franchise=>{
    setLoading(true);setError('');setNotice('');setSelectedFranchise(franchise)
    const scope=String(franchise.id)
    try{
      setEmployees(await getCommissionEmployees(scope))
    }catch(x){setError(x.message)}finally{setLoading(false)}
  }

  useEffect(()=>{
    const id=Number(sessionStorage.getItem('commissionFocusId')||0)
    if(!id||isSuper||!employees.length||!canReview)return
    let activeRequest=true
    ;(async()=>{
      try{
        const entry=await getCommissionEntry(id)
        if(!entry||!activeRequest)return
        const employee=employees.find(item=>Number(item.user_id)===Number(entry.employee_user_id))
        if(isFranchiseScope&&employee)await openEmployee(employee)
        if(!activeRequest)return
        sessionStorage.removeItem('commissionFocusId')
        await openReview(entry)
      }catch(x){
        if(activeRequest)setError(x.message||'The commission notification could not be opened.')
      }
    })()
    return()=>{activeRequest=false}
  },[employees])

  const staffButton=(employee,nested=false)=><button type="button" className={`commission-employee-row${nested?' nested':''}`} key={employee.user_id} onClick={()=>openEmployee(employee)}><div><strong>{employee.full_name}</strong><span>{employee.employee_role||'Employee'}{employee.employee_number?` · ${employee.employee_number}`:''}</span></div><span className="commission-open-label">Open commissions →</span></button>
  const viewingLinkedEmployee=isManager&&selectedEmployee?.staff_type==='employee'

  if(editing){
    return <section className="stack-page staff-commission-page commission-review-page"><div className="commission-review-workspace"><div className="section-heading"><div><button type="button" className="glass-button" onClick={closeReview}>← Back to commissions</button><p className="eyebrow">Approval document</p><h1>Review commission #{editing.id}</h1><p>{editing.employee_name} · {editing.reference}</p></div></div>{error&&<div className="error-message">{error}</div>}{reviewPdfUrl?<div className="pdf-preview commission-review-pdf"><iframe src={reviewPdfUrl} title={`Commission review ${editing.id}`}/></div>:<p>Preparing review PDF...</p>}<div className="commission-review-decision"><label>Deceased name and surname<input required value={editing.claim_deceased || ''} onChange={e => setEditing(v => ({...v,claim_deceased:e.target.value}))}/></label><label>Service role<select value={editing.commission_role || 'driver'} onChange={e => setEditing(v => ({...v,commission_role:e.target.value}))}><option value="driver">Employee</option><option value="assistant">Assistant</option></select></label><label>Decision notes<textarea placeholder="Add an approval or rejection note" value={editing.review_notes||''} onChange={e=>setEditing(v=>({...v,review_notes:e.target.value}))}/></label><div className="button-row"><button className="primary-button" onClick={()=>review('approved')}>Approve claim</button><button className="danger-button" onClick={()=>review('rejected')}>Reject claim</button></div></div></div></section>
  }

  if(isSuper&&!selectedFranchise){
    return <section className="card attendance-tab-panel staff-commission-page"><div className="tab-page-section"><h1>Franchise Commissions</h1><p>Select a franchise user to view only that franchise’s managers, employees and commission history.</p>{error&&<div className="error-message">{error}</div>}</div><div className="tab-page-section"><h2>Franchise Users</h2>{loading?<p>Loading franchise users...</p>:<div className="commission-employee-list">{franchises.map(f=><button type="button" className="commission-employee-row" key={f.id} onClick={()=>openFranchise(f)}><div><strong>{f.franchise_name||f.business_name||f.full_name||`Franchise ${f.id}`}</strong><span>{f.username||f.email||'Franchise user'}</span></div><span className="commission-open-label">Open commissions →</span></button>)}{!franchises.length&&<div className="empty-state">No active franchise users found.</div>}</div>}</div></section>
  }

  if(isFranchiseScope && !selectedEmployee){
    return <section className="card attendance-tab-panel staff-commission-page">
      <header className="tab-page-intro"><h3>Commission Claims</h3><p>Select a manager or employee to view their commissions and document status.</p></header>
      {isSuper&&<button type="button" className="glass-button" onClick={()=>{setSelectedFranchise(null);setEmployees([])}}>← Franchise users</button>}{error&&<div className="error-message">{error}</div>}{notice&&<div className="success-message">{notice}</div>}
      <div className="tab-page-section"><div className="section-heading"><div><h2>Managers and linked employees</h2><p>Select a manager for their own commissions, or select an employee listed beneath that manager.</p></div><label className="commission-employee-search">Search staff<input value={employeeSearch} onChange={e=>setEmployeeSearch(e.target.value)} placeholder="Name, role, number or email"/></label></div>
        {loading?<p>Loading employees...</p>:<div className="commission-hierarchy-list">{staffHierarchy.groups.map(group=><section className="commission-manager-group" key={group.manager.user_id}><div className="commission-manager-heading">{staffButton(group.manager)}<span>{group.employees.length} linked employee{group.employees.length===1?'':'s'}</span></div><div className="commission-linked-employees">{group.employees.map(employee=>staffButton(employee,true))}{!group.employees.length&&<small className="muted">No linked employees.</small>}</div></section>)}{staffHierarchy.direct.length>0&&<section className="commission-manager-group"><h3>Direct employees</h3><div className="commission-linked-employees">{staffHierarchy.direct.map(employee=>staffButton(employee,true))}</div></section>}{!staffHierarchy.groups.length&&!staffHierarchy.direct.length&&<div className="empty-state">No registered staff found.</div>}</div>}
      </div>
    </section>
  }

  return <section className="card attendance-tab-panel staff-commission-page">
    <div className="tab-page-section"><div className="section-heading"><div>{selectedEmployee&&<button type="button" className="glass-button" onClick={closeEmployee}>{isManager?'← My commissions':'← All employees'}</button>}<h1>{selectedEmployee?`${selectedEmployee.full_name} — Commissions`:'My Commissions'}</h1><p>{selectedEmployee?`${selectedEmployee.employee_role||'Employee'}${selectedEmployee.employee_number?` · ${selectedEmployee.employee_number}`:''}`:isSelfSubmitter?'View commissions and submit service claims.':'View this staff member’s commissions and document status.'}</p></div></div>{error&&<div className="error-message">{error}</div>}{notice&&<div className="success-message">{notice}</div>}</div>



    <StaffCommissionOverview employeeId={selectedEmployee?.user_id || me.id} franchiseId={selectedFranchise?.id} refreshKey={overviewKey} me={me} onReview={openReview} onHistory={async entry => setHistory({entry,items:await getCommissionEntryHistory(entry.id)})}/>
    {!viewingLinkedEmployee && <details className="commission-add-claim"><summary>Add a service commission</summary><ServiceClaimPanel me={me} employee={selectedEmployee} franchiseId={selectedFranchise?.id} onSaved={refresh}/></details>}

    {isManager&&!selectedEmployee&&<div className="tab-page-section"><div className="section-heading"><div><h2>Employees linked to me</h2><p>Your totals above contain only your own commission. Select an employee to view that employee’s claims. Qualifying commissions approve automatically.</p></div></div><div className="commission-employee-list">{linkedEmployees.map(employee=>staffButton(employee))}{!linkedEmployees.length&&<div className="empty-state">No employees are linked to this manager.</div>}</div></div>}

    {history&&<div className="tab-page-section"><div className="section-heading"><h2>Audit history — {history.entry.reference}</h2><button className="glass-button" onClick={()=>setHistory(null)}>Close</button></div><div className="table-wrap"><table><thead><tr><th>Date</th><th>Action</th><th>Actor</th><th>Note</th></tr></thead><tbody>{history.items.map(x=><tr key={x.id}><td>{new Date(x.created_at).toLocaleString('en-ZA')}</td><td>{x.action.replaceAll('_',' ')}</td><td>{x.actor_name}</td><td>{x.note||'—'}</td></tr>)}</tbody></table></div></div>}
  </section>
}
