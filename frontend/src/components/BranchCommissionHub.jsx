import { useEffect, useState } from 'react'
import { apiRequest, apiBlob, getCommissionEntries } from '../api/client'
import MonthlyCommissionStatement from './MonthlyCommissionStatement'
import CommissionCheckboxes, { commissionLabels } from './CommissionCheckboxes'

const currentMonth = () => new Date(Date.now() + 7200000).toISOString().slice(0, 7)
const actionTitles = { permissions: 'Commission permissions', monthly: 'Monthly commissions', pdf: 'Employee PDF' }

function EmployeePdfPage({ franchiseId, employee, branch, month, onMonthChange }) {
  const [url, setUrl] = useState(''), [error, setError] = useState('')
  useEffect(() => {
    let active = true, objectUrl
    setUrl(''); setError('')
    const query = new URLSearchParams({ month, employee_user_id: employee.user_id, branch_id: branch.id,
      ...(franchiseId ? { franchise_user_id: franchiseId } : {}) })
    apiBlob(`/receipt-commissions/report.pdf?${query}`).then(blob => {
      if (active) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl) }
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [franchiseId, employee.user_id, branch.id, month])
  return <section className="form-card staff-pdf-page">
    <label>Report month<input type="month" required value={month} onChange={e => { if (e.target.value) onMonthChange(e.target.value) }}/></label>
    {error ? <p role="alert" className="error-message">{error}</p> : url ? <>
      <a className="staff-download-link" href={url} download={`commissions-${month}.pdf`}>Download Employee PDF</a>
      <iframe title={`Commission PDF for ${employee.full_name} at ${branch.name}`} src={url}/>
    </> : <p role="status">Preparing employee PDF…</p>}
  </section>
}

export default function BranchCommissionHub({ franchiseId, branchId = '', onBranchChange, route = {}, onNavigate }) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [month, setMonth] = useState(currentMonth)
  const [editor, setEditor] = useState(null), [busy, setBusy] = useState(false), [saved, setSaved] = useState('')
  const [earnings, setEarnings] = useState(null), [earningsError, setEarningsError] = useState('')
  const activeBranch = String(branchId || '')
  const suffix = franchiseId ? `?franchise_user_id=${franchiseId}` : ''
  const action = route.action
  const branch = data?.branches.find(b => String(b.id) === route.branch)
  const employee = data?.employees.find(e => String(e.user_id) === route.employee)
  const load = async () => setData(await apiRequest(`/receipt-commissions/settings${suffix}`))
  useEffect(() => { let active = true; setData(null); setError(''); apiRequest(`/receipt-commissions/settings${suffix}`).then(d => { if (active) setData(d) }).catch(e => { if (active) setError(e.message) }); return () => { active = false } }, [suffix])
  useEffect(() => {
    let active = true
    setEarnings(null); setEarningsError('')
    if (!/^\d{4}-\d{2}$/.test(month)) return undefined
    const [year, number] = month.split('-').map(Number)
    const loadEarnings = () => getCommissionEntries({ franchiseUserId: franchiseId, fromDate: `${month}-01`, toDate: new Date(Date.UTC(year, number, 0)).toISOString().slice(0, 10) })
      .then(result => { if (active) { setEarnings([...result.items,...(result.pending_imports||[])]); setEarningsError('') } })
      .catch(e => { if (active) setEarningsError(e.message) })
    loadEarnings()
    const timer = setInterval(loadEarnings, 20000)
    return () => { active = false; clearInterval(timer) }
  }, [franchiseId, activeBranch, month])
  const commissionSummary = (person, branch) => {
    if (earningsError) return 'Commissions unavailable'
    if (!earnings) return 'Loading commissions…'
    const rows = earnings.filter(r => Number(r.employee_user_id) === Number(person.user_id) && Number(r.earning_branch_id) === Number(branch.id))
    const approved = rows.filter(row => row.status === 'approved' && row.payment_eligible).reduce((sum, row) => sum + Number(row.calculated_amount || 0), 0)
    const awaiting = rows.filter(row => ['pending', 'approved'].includes(row.status) && !row.payment_eligible).reduce((sum, row) => sum + Number(row.expected_amount ?? row.calculated_amount ?? 0), 0)
    const money = value => `R ${value.toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    return <><strong>Approved: {money(approved)}</strong><span className="commission-awaiting-badge">Awaiting document checks: {money(awaiting)}</span></>
  }
  const approvedTotal=branch=>earnings?.filter(r=>r.status==='approved'&&r.payment_eligible&&(!branch||Number(r.earning_branch_id)===Number(branch))).reduce((n,r)=>n+Number(r.calculated_amount||0),0)
  const totalLabel=value=>value==null?'Loading…':`R ${value.toLocaleString('en-ZA',{minimumFractionDigits:2,maximumFractionDigits:2})}`
  useEffect(() => {
    let active = true
    setEditor(null); setError(''); setSaved('')
    if (action === 'permissions' && employee && branch) {
      apiRequest(`/receipt-commissions/options/${employee.user_id}`).then(preferences => {
        if (active) setEditor({ preferences, values: preferences.commission_branches || {} })
      }).catch(e => { if (active) setError(e.message) })
    }
    return () => { active = false }
  }, [action, employee?.user_id, branch?.id, suffix])
  const enabled = (e, bid) => e.commission_branches?.[String(bid)]?.enabled_types || []
  const members = b => data.employees.filter(e => e.branch_id === b.id || enabled(e, b.id).length)
  const open = (nextAction, person, location) => onNavigate('branches', { action: nextAction, employee: person.user_id, branch: location.id })
  const save = async () => {
    setBusy(true); setError(''); setSaved('')
    try {
      await apiRequest('/receipt-commissions/options', { method: 'PUT', body: JSON.stringify({ employee_user_id: employee.user_id,
        franchise_user_id: data.franchise_user_id, commission_branches: editor.values,
        receipt_percentage: editor.preferences.options.invoice_commission?.rate ?? null }) })
      await load(); setSaved(`Commission permissions saved for ${employee.full_name} at ${branch.name}.`)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const download = async selectedBranch => {
    try {
      const query = new URLSearchParams({ month, ...(franchiseId ? { franchise_user_id: franchiseId } : {}), ...(selectedBranch ? { branch_id: selectedBranch } : {}) })
      const blob = await apiBlob(`/receipt-commissions/report.pdf?${query}`), url = URL.createObjectURL(blob), link = document.createElement('a')
      link.href = url; link.download = `commissions-${month}.pdf`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) { setError(e.message) }
  }

  if (action) return <section className="mortuary-book staff-commission-detail">
    <header className="form-card"><button type="button" className="glass-button" onClick={() => onNavigate('branches')}>← All Branches &amp; Commissions</button>
      <h2>{actionTitles[action] || 'Commission page'}</h2>{employee && branch && <p><strong>{employee.full_name}</strong> · {employee.employee_role} · {branch.name}</p>}
    </header>
    {error && <p role="alert" className="error-message">{error}</p>}
    {!data && !error && <p role="status">Loading staff details…</p>}
    {data && (!employee || !branch || !actionTitles[action]) && <p role="alert">This employee, branch or commission page is unavailable. Return to the branch list and select an active staff member.</p>}
    {employee && branch && action === 'permissions' && (editor ? <section className="form-card">
      <CommissionCheckboxes branches={[branch]} branchOptions={editor.values} onBranchOptionsChange={values => { setEditor(v => ({ ...v, values })); setSaved('') }}/>
      <div className="button-row"><button type="button" disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save this commission'}</button>
        <button type="button" className="glass-button" disabled={busy} onClick={() => onNavigate('branches')}>Back to branches</button></div>
      {saved && <p role="status" className="success">{saved}</p>}
    </section> : !error && <p role="status">Loading commission permissions…</p>)}
    {employee && branch && action === 'monthly' && <section className="form-card"><MonthlyCommissionStatement employeeUserId={employee.user_id} franchiseId={franchiseId} earningBranchId={branch.id}/></section>}
    {employee && branch && action === 'pdf' && <EmployeePdfPage franchiseId={franchiseId} employee={employee} branch={branch} month={month} onMonthChange={setMonth}/>}
  </section>

  return <section className="mortuary-book commission-branch-hub">
    <div className="form-card"><h2>All Branches &amp; Commissions</h2><p>All managers and employees are listed below with their commissions for the selected month. Only approved entries with both service and payment proof contribute to totals.</p>
      <div className="mortuary-rates"><label>Branch view<select value={activeBranch} onChange={e => onBranchChange?.(e.target.value)}><option value="">All linked branches</option>{data?.branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
        <label>Report month<input type="month" value={month} onChange={e => { if (e.target.value) setMonth(e.target.value) }}/></label></div>
      <button type="button" className="glass-button" onClick={() => download(activeBranch)}>Download {activeBranch ? 'selected branch' : 'all branches'} PDF</button>
      {error && <p role="alert" className="error-message">{error}</p>}{!data && !error && <p role="status">Loading linked branches…</p>}
      {earningsError && <p role="alert" className="error-message">{earningsError}</p>}
      <strong>Combined approved total · all linked branches: {earningsError?'Unavailable':totalLabel(approvedTotal())}</strong>
    </div>
    {data?.branches.filter(b => !activeBranch || String(b.id) === activeBranch).map(b => <section className="form-card" key={b.id}>
      <strong>Branch approved total: {earningsError?'Unavailable':totalLabel(approvedTotal(b.id))}</strong>
      <div className="section-heading"><h3>{b.name}</h3><div className="button-row">{!activeBranch && <button type="button" className="glass-button" onClick={() => onBranchChange?.(String(b.id))}>Open this branch</button>}<button type="button" onClick={() => download(b.id)}>Branch commission PDF</button></div></div>
      {members(b).map(e => <div className="branch-staff-row" key={e.user_id}><div><strong>{e.full_name} · {e.employee_role}</strong><small className="commission-branch-summary">Home branch: {e.branch_name}<br/>Enabled here: {enabled(e, b.id).map(c => commissionLabels[c]).join(', ') || 'No commissions enabled'}<br/>{commissionSummary(e, b)}</small></div>
        <div className="branch-staff-actions"><button type="button" className="glass-button" onClick={() => open('permissions', e, b)}>Commission permissions</button>
        <button type="button" className="glass-button" onClick={() => open('monthly', e, b)}>Monthly commissions</button>
        <button type="button" className="glass-button" onClick={() => open('pdf', e, b)}>Employee PDF</button></div></div>)}
      {!members(b).length && <p>No active staff are assigned to or enabled for commissions at this branch.</p>}
    </section>)}
  </section>
}
