import { useEffect, useMemo, useState } from 'react'
import {
  createCommissionEntry, deleteCommissionEntry, downloadCommissionReport,
  getCommissionEmployees, getCommissionEntries, getCommissionStructures,
  getCommissionTypes, saveCommissionStructure,
} from '../api/client'

const money = (value) => `R ${Number(value || 0).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export default function CommissionPage({ me }) {
  const canManage = me.roles.includes('FranchiseUser') || me.roles.includes('SuperUser')
  const [types, setTypes] = useState([])
  const [employees, setEmployees] = useState([])
  const [structures, setStructures] = useState([])
  const [report, setReport] = useState({ items: [], total: 0, commission_total: 0, overtime_total: 0 })
  const [filter, setFilter] = useState({ employeeUserId: '', fromDate: '', toDate: '' })
  const [form, setForm] = useState({ employee_user_id: '', commission_type: 'removals', service_date: new Date().toISOString().slice(0,10), reference: '', quantity: 1, invoice_value_before_tax: '', hours: '', hourly_rate: '', notes: '' })
  const [structure, setStructure] = useState({ commission_type: 'removals', label: 'Removals', calculation_type: 'fixed', rate: 0, overtime_multiplier: 1.5, is_active: true })
  const [error, setError] = useState('')

  const load = async () => {
    try {
      setError('')
      const [t, e, s] = await Promise.all([getCommissionTypes(), getCommissionEmployees(), getCommissionStructures()])
      setTypes(t); setEmployees(e); setStructures(s)
      const r = await getCommissionEntries(filter)
      setReport(r)
      if (!form.employee_user_id && e.length === 1) setForm((v) => ({ ...v, employee_user_id: String(e[0].user_id) }))
    } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [])

  const currentStructure = useMemo(() => structures.find((s) => s.commission_type === form.commission_type), [structures, form.commission_type])
  const refreshReport = async () => { try { setReport(await getCommissionEntries(filter)); setError('') } catch (err) { setError(err.message) } }

  const submitEntry = async (event) => {
    event.preventDefault()
    try {
      await createCommissionEntry({
        ...form,
        employee_user_id: Number(form.employee_user_id), quantity: Number(form.quantity || 1),
        invoice_value_before_tax: form.invoice_value_before_tax === '' ? null : Number(form.invoice_value_before_tax),
        hours: form.hours === '' ? null : Number(form.hours), hourly_rate: form.hourly_rate === '' ? null : Number(form.hourly_rate),
      })
      setForm((v) => ({ ...v, reference: '', quantity: 1, invoice_value_before_tax: '', hours: '', hourly_rate: '', notes: '' }))
      await refreshReport()
    } catch (err) { setError(err.message) }
  }

  const submitStructure = async (event) => {
    event.preventDefault()
    try {
      await saveCommissionStructure({ ...structure, rate: Number(structure.rate || 0), overtime_multiplier: structure.calculation_type === 'overtime' ? Number(structure.overtime_multiplier || 1) : null })
      setStructures(await getCommissionStructures()); setError('')
    } catch (err) { setError(err.message) }
  }

  const exportPdf = async () => {
    try {
      const blob = await downloadCommissionReport(filter)
      const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'commission-overtime-report.pdf'; a.click(); URL.revokeObjectURL(url)
    } catch (err) { setError(err.message) }
  }

  return <section className="stack-page">
    <div className="glass-card section-card">
      <div className="section-heading"><div><h1>Commission & Overtime</h1><p>{canManage ? 'Manage employee commission and overtime for your franchise.' : 'Your personal commission and overtime report.'}</p></div></div>
      {error ? <div className="error-message">{error}</div> : null}
      <div className="stats-grid">
        <div className="stat-card"><span>Total</span><strong>{money(report.total)}</strong></div>
        <div className="stat-card"><span>Commission</span><strong>{money(report.commission_total)}</strong></div>
        <div className="stat-card"><span>Overtime</span><strong>{money(report.overtime_total)}</strong></div>
      </div>
    </div>

    {canManage ? <div className="glass-card section-card">
      <h2>Commission structure</h2>
      <form className="form-grid" onSubmit={submitStructure}>
        <label>Type<select value={structure.commission_type} onChange={(e) => { const t=types.find(x=>x.value===e.target.value); setStructure((v)=>({...v,commission_type:e.target.value,label:t?.label||'',calculation_type:e.target.value==='invoice_commission'?'percentage':e.target.value==='overtime'?'overtime':'fixed'})) }}>{types.map(t=><option key={t.value} value={t.value}>{t.label}</option>)}</select></label>
        <label>Label<input value={structure.label} onChange={(e)=>setStructure((v)=>({...v,label:e.target.value}))}/></label>
        <label>{structure.calculation_type === 'percentage' ? 'Percentage' : structure.calculation_type === 'overtime' ? 'Default hourly rate (optional)' : 'Fixed amount'}<input type="number" step="0.01" min="0" value={structure.rate} onChange={(e)=>setStructure((v)=>({...v,rate:e.target.value}))}/></label>
        {structure.calculation_type === 'overtime' ? <label>Overtime multiplier<input type="number" step="0.01" min="0" value={structure.overtime_multiplier} onChange={(e)=>setStructure((v)=>({...v,overtime_multiplier:e.target.value}))}/></label> : null}
        <button className="primary-button" type="submit">Save structure</button>
      </form>
      {structures.length ? <div className="table-wrap"><table><thead><tr><th>Type</th><th>Calculation</th><th>Rate</th></tr></thead><tbody>{structures.map(s=><tr key={s.id}><td>{s.label}</td><td>{s.calculation_type}</td><td>{s.calculation_type==='percentage'?`${s.rate}%`:s.calculation_type==='overtime'?`${s.overtime_multiplier || s.rate}x`:money(s.rate)}</td></tr>)}</tbody></table></div> : null}
    </div> : null}

    {canManage ? <div className="glass-card section-card"><h2>Add employee entry</h2><form className="form-grid" onSubmit={submitEntry}>
      <label>Employee<select required value={form.employee_user_id} onChange={(e)=>setForm((v)=>({...v,employee_user_id:e.target.value}))}><option value="">Select employee</option>{employees.map(e=><option key={e.user_id} value={e.user_id}>{e.full_name}</option>)}</select></label>
      <label>Type<select value={form.commission_type} onChange={(e)=>setForm((v)=>({...v,commission_type:e.target.value}))}>{types.map(t=><option key={t.value} value={t.value}>{t.label}</option>)}</select></label>
      <label>Date<input required type="date" value={form.service_date} onChange={(e)=>setForm((v)=>({...v,service_date:e.target.value}))}/></label>
      <label>Reference<input value={form.reference} onChange={(e)=>setForm((v)=>({...v,reference:e.target.value}))}/></label>
      {form.commission_type === 'invoice_commission' ? <label>Invoice value before TAX<input required type="number" step="0.01" min="0" value={form.invoice_value_before_tax} onChange={(e)=>setForm((v)=>({...v,invoice_value_before_tax:e.target.value}))}/></label> : null}
      {form.commission_type === 'overtime' ? <><label>Overtime hours<input required type="number" step="0.25" min="0" value={form.hours} onChange={(e)=>setForm((v)=>({...v,hours:e.target.value}))}/></label><label>Hourly rate<input required type="number" step="0.01" min="0" value={form.hourly_rate} onChange={(e)=>setForm((v)=>({...v,hourly_rate:e.target.value}))}/></label></> : null}
      {!['invoice_commission','overtime'].includes(form.commission_type) ? <label>Quantity<input required type="number" step="1" min="1" value={form.quantity} onChange={(e)=>setForm((v)=>({...v,quantity:e.target.value}))}/></label> : null}
      <label className="full-width">Notes<textarea value={form.notes} onChange={(e)=>setForm((v)=>({...v,notes:e.target.value}))}/></label>
      <button className="primary-button" type="submit" disabled={!currentStructure}>Add entry</button>{!currentStructure ? <span>Create this structure first.</span> : null}
    </form></div> : null}

    <div className="glass-card section-card"><div className="section-heading"><h2>{canManage ? 'Employee report' : 'My report'}</h2><button className="glass-button" onClick={exportPdf}>Export PDF</button></div>
      <div className="form-grid compact-grid">{canManage ? <label>Employee<select value={filter.employeeUserId} onChange={(e)=>setFilter((v)=>({...v,employeeUserId:e.target.value}))}><option value="">All employees</option>{employees.map(e=><option key={e.user_id} value={e.user_id}>{e.full_name}</option>)}</select></label> : null}<label>From<input type="date" value={filter.fromDate} onChange={(e)=>setFilter((v)=>({...v,fromDate:e.target.value}))}/></label><label>To<input type="date" value={filter.toDate} onChange={(e)=>setFilter((v)=>({...v,toDate:e.target.value}))}/></label><button className="glass-button" onClick={refreshReport}>Apply</button></div>
      <div className="table-wrap"><table><thead><tr><th>Date</th>{canManage ? <th>Employee</th> : null}<th>Type</th><th>Reference</th><th>Details</th><th>Amount</th>{canManage ? <th>Action</th> : null}</tr></thead><tbody>{report.items.map(r=><tr key={r.id}><td>{r.service_date}</td>{canManage ? <td>{r.employee_name}</td> : null}<td>{r.commission_type.replaceAll('_',' ')}</td><td>{r.reference || '-'}</td><td>{r.commission_type==='overtime'?`${r.hours} hrs × ${money(r.hourly_rate)} × ${r.applied_rate}`:r.commission_type==='invoice_commission'?`${money(r.invoice_value_before_tax)} × ${r.applied_rate}%`:`${r.quantity} × ${money(r.applied_rate)}`}</td><td>{money(r.calculated_amount)}</td>{canManage ? <td><button className="danger-button" onClick={async()=>{await deleteCommissionEntry(r.id); await refreshReport()}}>Delete</button></td> : null}</tr>)}{!report.items.length ? <tr><td colSpan="7">No records found.</td></tr> : null}</tbody></table></div>
    </div>
  </section>
}
