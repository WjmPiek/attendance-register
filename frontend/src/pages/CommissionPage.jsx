import { useEffect, useMemo, useState } from 'react'
import {
  bulkReviewCommissionEntries, createCommissionEntry, deleteCommissionEntry, downloadCommissionForm,
  downloadCommissionReport, getCommissionEmployees, getCommissionEntries, getCommissionStructures,
  getCommissionTypes, reviewCommissionEntry, saveCommissionStructure,
} from '../api/client'

const today = () => new Date().toISOString().slice(0, 10)
const money = (v) => `R ${Number(v || 0).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const blank = { employee_user_id:'', commission_type:'removals', service_date:today(), reference:'', quantity:1, invoice_value_before_tax:'', hours:'', hourly_rate:'', notes:'' }
const emptyReport = {items:[],total:0,commission_total:0,overtime_total:0,counts:{}}

export default function CommissionPage({ me }) {
  const isEmployee = me.roles.includes('EmployeeUser')
  const isFranchise = me.roles.includes('FranchiseUser')
  const canReview = me.roles.some(r => ['FranchiseUser','ManagerUser','SuperUser'].includes(r))
  const canManageStructure = me.roles.some(r => ['FranchiseUser','SuperUser'].includes(r))
  const [types,setTypes]=useState([]), [employees,setEmployees]=useState([]), [structures,setStructures]=useState([])
  const [report,setReport]=useState(emptyReport)
  const [filter,setFilter]=useState({employeeUserId:'',fromDate:'',toDate:'',status:'',search:''})
  const [form,setForm]=useState(blank), [editing,setEditing]=useState(null), [selected,setSelected]=useState([])
  const [selectedEmployee,setSelectedEmployee]=useState(null)
  const [employeeSearch,setEmployeeSearch]=useState('')
  const [structure,setStructure]=useState({commission_type:'removals',label:'Removals',calculation_type:'fixed',rate:0,overtime_multiplier:1.5,is_active:true})
  const [error,setError]=useState(''), [notice,setNotice]=useState(''), [loading,setLoading]=useState(true)

  const refresh=async(f=filter)=>{ try{setReport(await getCommissionEntries(f));setError('')}catch(e){setError(e.message)} }
  const load=async()=>{
    setLoading(true)
    const results = await Promise.allSettled([getCommissionTypes(),getCommissionEmployees(),getCommissionStructures()])
    const [t,e,s] = results
    if(t.status==='fulfilled') setTypes(t.value); else setError(t.reason?.message || 'Commission types could not load.')
    if(e.status==='fulfilled') {
      setEmployees(e.value)
      if(isEmployee && e.value.length===1) setForm(v=>({...v,employee_user_id:String(e.value[0].user_id)}))
    } else setError(e.reason?.message || 'Employees could not load.')
    if(s.status==='fulfilled') setStructures(s.value); else setError(s.reason?.message || 'Commission structures could not load.')
    if(!isFranchise) await refresh()
    setLoading(false)
  }
  useEffect(()=>{load()},[])
  useEffect(()=>{const id=Number(sessionStorage.getItem('commissionFocusId')||0);if(id){sessionStorage.removeItem('commissionFocusId');getCommissionEntries({}).then(r=>{const x=r.items.find(i=>i.id===id);if(x)setEditing(x)})}},[])

  const active=useMemo(()=>structures.filter(s=>s.is_active),[structures])
  const current=active.find(s=>s.commission_type===form.commission_type)
  const filteredEmployees=useMemo(()=>{
    const q=employeeSearch.trim().toLowerCase()
    if(!q)return employees
    return employees.filter(x=>[x.full_name,x.employee_number,x.employee_role,x.email,x.office_address_assigned].some(v=>String(v||'').toLowerCase().includes(q)))
  },[employees,employeeSearch])
  const estimate=()=>{if(!current)return 0;if(form.commission_type==='invoice_commission')return Number(form.invoice_value_before_tax||0)*Number(current.rate||0)/100;if(form.commission_type==='overtime')return Number(form.hours||0)*Number(form.hourly_rate||0)*Number(current.overtime_multiplier||current.rate||1);return Number(form.quantity||0)*Number(current.rate||0)}
  const payload=(x)=>({...x,employee_user_id:x.employee_user_id?Number(x.employee_user_id):null,quantity:Number(x.quantity||1),invoice_value_before_tax:x.invoice_value_before_tax===''?null:Number(x.invoice_value_before_tax),hours:x.hours===''?null:Number(x.hours),hourly_rate:x.hourly_rate===''?null:Number(x.hourly_rate)})
  const submit=async e=>{e.preventDefault();try{await createCommissionEntry(payload(form));setForm(v=>({...blank,employee_user_id:v.employee_user_id}));setNotice(isEmployee?'Commission submitted for review.':'Commission added for this employee.');await refresh(filter)}catch(x){setError(x.message)}}
  const saveStructure=async e=>{e.preventDefault();try{await saveCommissionStructure({...structure,rate:Number(structure.rate||0),overtime_multiplier:structure.calculation_type==='overtime'?Number(structure.overtime_multiplier||1):null});setStructures(await getCommissionStructures());setNotice('Structure saved.')}catch(x){setError(x.message)}}
  const review=async status=>{try{await reviewCommissionEntry(editing.id,{...payload(editing),status,review_notes:editing.review_notes||''});setEditing(null);setNotice(`Commission ${status}. Employee notification sent.`);await refresh(filter)}catch(x){setError(x.message)}}
  const bulk=async status=>{if(!selected.length)return;try{const count=selected.length;await bulkReviewCommissionEntries({entry_ids:selected,status,review_notes:''});setSelected([]);setNotice(`${count} submission(s) ${status}.`);await refresh(filter)}catch(x){setError(x.message)}}
  const saveBlob=(blob,name)=>{const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=name;a.click();URL.revokeObjectURL(u)}
  const openEmployee=async employee=>{
    const next={employeeUserId:String(employee.user_id),fromDate:'',toDate:'',status:'',search:''}
    setSelectedEmployee(employee);setForm({...blank,employee_user_id:String(employee.user_id)});setFilter(next);setSelected([]);setEditing(null);setNotice('');setError('')
    const url=new URL(window.location.href);url.searchParams.set('commission_employee',String(employee.user_id));window.history.replaceState({},'',url)
    await refresh(next)
  }
  const closeEmployee=()=>{
    setSelectedEmployee(null);setReport(emptyReport);setFilter({employeeUserId:'',fromDate:'',toDate:'',status:'',search:''});setSelected([]);setEditing(null)
    const url=new URL(window.location.href);url.searchParams.delete('commission_employee');window.history.replaceState({},'',url)
  }

  useEffect(()=>{
    if(!isFranchise || !employees.length || selectedEmployee)return
    const id=Number(new URLSearchParams(window.location.search).get('commission_employee')||0)
    const employee=employees.find(x=>Number(x.user_id)===id)
    if(employee)openEmployee(employee)
  },[employees,isFranchise])

  const structurePanel = canManageStructure && <div className="glass-card section-card"><h2>Commission structures</h2><form className="form-grid" onSubmit={saveStructure}><label>Type<select value={structure.commission_type} onChange={e=>{const t=types.find(x=>x.value===e.target.value);setStructure(v=>({...v,commission_type:e.target.value,label:t?.label||'',calculation_type:e.target.value==='invoice_commission'?'percentage':e.target.value==='overtime'?'overtime':'fixed'}))}}>{types.map(t=><option key={t.value} value={t.value}>{t.label}</option>)}</select></label><label>Display label<input required value={structure.label} onChange={e=>setStructure(v=>({...v,label:e.target.value}))}/></label><label>Rate<input type="number" min="0" step="0.01" value={structure.rate} onChange={e=>setStructure(v=>({...v,rate:e.target.value}))}/></label>{structure.calculation_type==='overtime'&&<label>Multiplier<input type="number" min="0" step="0.01" value={structure.overtime_multiplier} onChange={e=>setStructure(v=>({...v,overtime_multiplier:e.target.value}))}/></label>}<button className="primary-button">Save structure</button></form><div className="table-wrap"><table><thead><tr><th>Label</th><th>Calculation</th><th>Rate</th></tr></thead><tbody>{structures.map(s=><tr key={s.id}><td>{s.label}</td><td>{s.calculation_type}</td><td>{s.calculation_type==='percentage'?`${s.rate}%`:s.calculation_type==='overtime'?`${s.overtime_multiplier||s.rate}x`:money(s.rate)}</td></tr>)}</tbody></table></div></div>

  if(isFranchise && !selectedEmployee){
    return <section className="stack-page">
      <div className="glass-card section-card"><div className="section-heading"><div><h1>Employee Commissions</h1><p>Select an employee to open a dedicated commission page and add or review their commissions.</p></div></div>{error&&<div className="error-message">{error}</div>}{notice&&<div className="success-message">{notice}</div>}</div>
      {structurePanel}
      <div className="glass-card section-card"><div className="section-heading"><div><h2>Registered employees</h2><p>{employees.length} active staff member{employees.length===1?'':'s'} available.</p></div><label className="commission-employee-search">Search staff<input value={employeeSearch} onChange={e=>setEmployeeSearch(e.target.value)} placeholder="Name, role, number or email"/></label></div>
        {loading?<p>Loading employees...</p>:<div className="commission-employee-list">{filteredEmployees.map(employee=><button type="button" className="commission-employee-row" key={employee.user_id} onClick={()=>openEmployee(employee)}><div><strong>{employee.full_name}</strong><span>{employee.employee_role||'Employee'}{employee.employee_number?` · ${employee.employee_number}`:''}</span>{employee.office_address_assigned&&<small>{employee.office_address_assigned}</small>}</div><span className="commission-open-label">Open commissions →</span></button>)}{!filteredEmployees.length&&<div className="empty-state">No registered employees found.</div>}</div>}
      </div>
    </section>
  }

  return <section className="stack-page">
    <div className="glass-card section-card"><div className="section-heading"><div>{selectedEmployee&&<button type="button" className="glass-button" onClick={closeEmployee}>← All employees</button>}<h1>{selectedEmployee?`${selectedEmployee.full_name} — Commissions`:'Commissions & Overtime'}</h1><p>{selectedEmployee?`${selectedEmployee.employee_role||'Employee'}${selectedEmployee.employee_number?` · ${selectedEmployee.employee_number}`:''}`:isEmployee?'Submit claims and track review status.':'Configure, review, approve and report on submissions.'}</p></div></div>{error&&<div className="error-message">{error}</div>}{notice&&<div className="success-message">{notice}</div>}<div className="stats-grid"><div className="stat-card"><span>Approved total</span><strong>{money(report.total)}</strong></div><div className="stat-card"><span>Pending</span><strong>{report.counts?.pending||0}</strong></div><div className="stat-card"><span>Approved</span><strong>{report.counts?.approved||0}</strong></div><div className="stat-card"><span>Rejected</span><strong>{report.counts?.rejected||0}</strong></div></div></div>

    {!selectedEmployee&&structurePanel}

    <div className="glass-card section-card"><h2>{isEmployee?'Submit commission form':selectedEmployee?`Add commission for ${selectedEmployee.full_name}`:'Add approved employee entry'}</h2><form className="form-grid" onSubmit={submit}>{!isEmployee&&!selectedEmployee&&<label>Employee<select required value={form.employee_user_id} onChange={e=>setForm(v=>({...v,employee_user_id:e.target.value}))}><option value="">Select employee</option>{employees.map(x=><option key={x.user_id} value={x.user_id}>{x.full_name}</option>)}</select></label>}<label>Commission<select value={form.commission_type} onChange={e=>setForm(v=>({...v,commission_type:e.target.value}))}>{active.map(x=><option key={x.id} value={x.commission_type}>{x.label}</option>)}</select></label><label>Service date<input required type="date" value={form.service_date} onChange={e=>setForm(v=>({...v,service_date:e.target.value}))}/></label><label>Reference number<input required value={form.reference} onChange={e=>setForm(v=>({...v,reference:e.target.value}))}/></label>{form.commission_type==='invoice_commission'?<label>Invoice value before tax<input required type="number" min="0" step="0.01" value={form.invoice_value_before_tax} onChange={e=>setForm(v=>({...v,invoice_value_before_tax:e.target.value}))}/></label>:form.commission_type==='overtime'?<><label>Hours<input required type="number" min="0" step="0.25" value={form.hours} onChange={e=>setForm(v=>({...v,hours:e.target.value}))}/></label><label>Hourly rate<input required type="number" min="0" step="0.01" value={form.hourly_rate} onChange={e=>setForm(v=>({...v,hourly_rate:e.target.value}))}/></label></>:<label>Quantity<input required type="number" min="1" step="1" value={form.quantity} onChange={e=>setForm(v=>({...v,quantity:e.target.value}))}/></label>}<label className="full-width">Notes<textarea value={form.notes} onChange={e=>setForm(v=>({...v,notes:e.target.value}))}/></label><div><strong>Calculated amount: {money(estimate())}</strong></div><button className="primary-button" disabled={!current||(!isEmployee&&!form.employee_user_id)}>{isEmployee?'Submit for review':'Add approved entry'}</button></form></div>

    <div className="glass-card section-card"><div className="section-heading"><h2>{canReview?'Commission history':'My submissions'}</h2><button className="glass-button" onClick={async()=>saveBlob(await downloadCommissionReport(filter),selectedEmployee?`${selectedEmployee.full_name}-commissions.pdf`:'commission-overtime-report.pdf')}>Download letterhead PDF</button></div><div className="form-grid compact-grid">{canReview&&!selectedEmployee&&<label>Employee<select value={filter.employeeUserId} onChange={e=>setFilter(v=>({...v,employeeUserId:e.target.value}))}><option value="">All</option>{employees.map(x=><option key={x.user_id} value={x.user_id}>{x.full_name}</option>)}</select></label>}<label>Status<select value={filter.status} onChange={e=>setFilter(v=>({...v,status:e.target.value}))}><option value="">All</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select></label><label>Search<input placeholder="Reference or type" value={filter.search} onChange={e=>setFilter(v=>({...v,search:e.target.value}))}/></label><label>From<input type="date" value={filter.fromDate} onChange={e=>setFilter(v=>({...v,fromDate:e.target.value}))}/></label><label>To<input type="date" value={filter.toDate} onChange={e=>setFilter(v=>({...v,toDate:e.target.value}))}/></label><button className="glass-button" onClick={()=>refresh(filter)}>Apply</button></div>{canReview&&selected.length>0&&<div className="button-row"><button className="primary-button" onClick={()=>bulk('approved')}>Approve selected</button><button className="danger-button" onClick={()=>bulk('rejected')}>Reject selected</button></div>}<div className="table-wrap"><table><thead><tr>{canReview&&<th>Select</th>}<th>Date</th>{canReview&&!selectedEmployee&&<th>Employee</th>}<th>Type</th><th>Reference</th><th>Qty</th><th>Amount</th><th>Status</th><th>Actions</th></tr></thead><tbody>{report.items.map(r=><tr key={r.id}>{canReview&&<td><input type="checkbox" disabled={r.status!=='pending'} checked={selected.includes(r.id)} onChange={e=>setSelected(v=>e.target.checked?[...v,r.id]:v.filter(id=>id!==r.id))}/></td>}<td>{r.service_date}</td>{canReview&&!selectedEmployee&&<td>{r.employee_name}</td>}<td>{r.commission_type.replaceAll('_',' ')}</td><td>{r.reference}</td><td>{r.quantity}</td><td>{money(r.calculated_amount)}</td><td><strong>{r.status}</strong></td><td><div className="button-row">{canReview&&r.status==='pending'&&<button className="glass-button" onClick={()=>setEditing({...r})}>Edit / review</button>}<button className="glass-button" onClick={async()=>saveBlob(await downloadCommissionForm(r.id),`commission-form-${r.id}.pdf`)}>PDF</button>{canManageStructure&&<button className="danger-button" onClick={async()=>{await deleteCommissionEntry(r.id);refresh(filter)}}>Delete</button>}</div></td></tr>)}{!report.items.length&&<tr><td colSpan="10">No commission records found for this employee.</td></tr>}</tbody></table></div></div>

    {editing&&<div className="glass-card section-card"><div className="section-heading"><h2>Review commission #{editing.id}</h2><button className="glass-button" onClick={()=>setEditing(null)}>Close</button></div><div className="form-grid"><label>Type<select value={editing.commission_type} onChange={e=>setEditing(v=>({...v,commission_type:e.target.value}))}>{active.map(x=><option key={x.id} value={x.commission_type}>{x.label}</option>)}</select></label><label>Date<input type="date" value={editing.service_date} onChange={e=>setEditing(v=>({...v,service_date:e.target.value}))}/></label><label>Reference<input value={editing.reference||''} onChange={e=>setEditing(v=>({...v,reference:e.target.value}))}/></label><label>Quantity<input type="number" min="1" value={editing.quantity||1} onChange={e=>setEditing(v=>({...v,quantity:e.target.value}))}/></label><label>Invoice value<input type="number" min="0" step="0.01" value={editing.invoice_value_before_tax||''} onChange={e=>setEditing(v=>({...v,invoice_value_before_tax:e.target.value}))}/></label><label>Hours<input type="number" min="0" step="0.25" value={editing.hours||''} onChange={e=>setEditing(v=>({...v,hours:e.target.value}))}/></label><label>Hourly rate<input type="number" min="0" step="0.01" value={editing.hourly_rate||''} onChange={e=>setEditing(v=>({...v,hourly_rate:e.target.value}))}/></label><label className="full-width">Employee notes<textarea value={editing.notes||''} onChange={e=>setEditing(v=>({...v,notes:e.target.value}))}/></label><label className="full-width">Review notes<textarea value={editing.review_notes||''} onChange={e=>setEditing(v=>({...v,review_notes:e.target.value}))}/></label><div className="button-row"><button className="primary-button" onClick={()=>review('approved')}>Save edits & approve</button><button className="danger-button" onClick={()=>review('rejected')}>Reject</button></div></div></div>}
  </section>
}
