import { useEffect, useState } from 'react'
import { apiRequest, getCommissionEntries } from '../api/client'
import { commissionLabels } from './CommissionCheckboxes'

const categories = ['full_funeral_service', 'church_service', 'grave_service', 'cremation_service', 'joinings', 'overtime']
const money = value => `R ${Number(value || 0).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const monthNow = () => new Date(Date.now() + 7200000).toISOString().slice(0, 7)

function MonthlyExpected({ employeeId, franchiseId, refreshKey }) {
  const [month, setMonth] = useState(monthNow), [rows, setRows] = useState([]), [error, setError] = useState('')
  useEffect(() => {
    if (!/^\d{4}-\d{2}$/.test(month)) return undefined
    let active = true
    const [year, number] = month.split('-').map(Number)
    const load = () => getCommissionEntries({ employeeUserId: employeeId, franchiseUserId: franchiseId, fromDate: `${month}-01`, toDate: new Date(Date.UTC(year, number, 0)).toISOString().slice(0, 10) }).then(data => { if (active) { setRows(data.items); setError('') } }).catch(e => { if (active) setError(e.message) })
    load()
    const timer = setInterval(load, 20000)
    return () => { active = false; clearInterval(timer) }
  }, [employeeId, franchiseId, month, refreshKey])
  const active = rows.filter(row => ['pending', 'approved'].includes(row.status))
  const valid = active.filter(row => row.payment_eligible)
  const approved = valid.filter(row => row.status === 'approved').reduce((sum, row) => sum + Number(row.calculated_amount), 0)
  const extraByCase = new Map()
  valid.filter(row => row.status === 'pending' && Number(row.expected_additional_fee) > 0).forEach(row => extraByCase.set(`${row.employee_user_id}:${row.expected_invoice_id}`, Number(row.expected_additional_fee)))
  const additional = [...extraByCase.values()].reduce((sum, amount) => sum + amount, 0)
  const waiting = valid.filter(row => row.status === 'pending').reduce((sum, row) => sum + Number(row.expected_amount ?? row.calculated_amount), additional)
  return <section className="form-card"><h2>Monthly expected commissions</h2><label>Month<input type="month" required value={month} onChange={e => setMonth(e.target.value)}/></label><p className="muted">Green amounts have matching, fully paid documents. Validated service claims approve automatically. Red amounts are potential commissions awaiting documents or correction.</p>{error ? <p role="alert" className="error-message">{error}</p> : <><div className="stats-grid"><div className="claim-validated"><span>Validated expected total</span><strong>{money(approved + waiting)}</strong></div><div className="stat-card"><span>Approved</span><strong>{money(approved)}</strong></div><div className="stat-card"><span>Validated, awaiting automatic approval</span><strong>{money(waiting)}</strong></div></div><div className="claim-status-list">{active.map(row => <article key={row.id} className={row.payment_eligible ? 'claim-validated' : 'claim-blocked'}><strong>{commissionLabels[row.commission_type] || row.commission_type} · {money(row.expected_amount ?? row.calculated_amount)}</strong>{Number(row.expected_additional_fee) > 0 && <p>Outside-branch fee: {money(row.expected_additional_fee)} (counted once per file in the total).</p>}<p>MF {row.reference} · {row.branch_name} · {row.service_date}</p><p>{row.payment_eligible ? row.status === 'approved' ? 'Approved' : 'Documents validated — automatic approval queued' : `Document uploads or corrections required: ${row.payment_block_reason}`}</p></article>)}{!active.length && <p>No commissions for the selected month.</p>}</div></>}</section>
}

export default function ServiceClaimPanel({ me, employee, franchiseId, onSaved }) {
  const uid = employee?.user_id || me.id
  const owner = me.roles.some(role => ['FranchiseUser', 'SuperUser'].includes(role))
  const initial = () => ({ commission_type: 'full_funeral_service', reference: '', claim_deceased: '', earning_branch_id: '', commission_role: 'driver', service_date: new Date(Date.now() + 7200000).toISOString().slice(0, 10), notes: '' })
  const [form, setForm] = useState(initial), [preferences, setPreferences] = useState(null), [external, setExternal] = useState([])
  const [quote, setQuote] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState(''), [refreshKey, setRefreshKey] = useState(0)
  useEffect(() => {
    let active = true
    setPreferences(null); setQuote(null); setForm(initial()); setError('')
    const suffix = franchiseId ? `?franchise_user_id=${franchiseId}` : ''
    Promise.all([apiRequest(`/receipt-commissions/options/${uid}`), apiRequest(`/receipt-commissions/external-branches${suffix}`)]).then(([options, outside]) => { if (active) { setPreferences(options); setExternal(outside.branches) } }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [uid, franchiseId])
  useEffect(() => {
    if (!preferences) return
    const first = categories.find(category => preferences.options?.[category]?.enabled) || ''
    setForm(old => preferences.options?.[old.commission_type]?.enabled ? old : { ...old, commission_type: first, earning_branch_id: '' })
  }, [preferences, form.commission_type])
  const enabled = category => preferences?.options?.[category]?.enabled
  const allowed = categories.filter(enabled)
  const branches = (preferences?.branches || []).filter(branch => preferences.commission_branches?.[String(branch.id)]?.enabled_types.includes(form.commission_type))
  const change = (field, value) => { setForm(old => ({ ...old, [field]: value, ...(field === 'commission_type' ? { earning_branch_id: '' } : {}) })); setQuote(null); setNotice('') }
  const request = () => ({ ...form, employee_user_id: uid, earning_branch_id: Number(form.earning_branch_id), quantity: 1 })
  const check = async event => {
    event.preventDefault(); setBusy(true); setError(''); setQuote(null)
    try { setQuote(await apiRequest('/commission/claim-quote', { method: 'POST', body: JSON.stringify(request()) })) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const save = async () => {
    setBusy(true); setError('')
    try {
      const result = await apiRequest('/commission/entries', { method: 'POST', body: JSON.stringify(request()) })
      setNotice(result.status === 'approved' ? 'Commission automatically approved.' : result.documents_valid ? 'Claim saved. Documents validated; automatic approval queued.' : 'Claim saved in red. Selected document uploaders have been notified.')
      setForm(initial()); setQuote(null); setRefreshKey(value => value + 1); await onSaved?.()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <section className="mortuary-book service-claim-panel"><section className="form-card"><h2>{owner && employee ? `Service claim for ${employee.full_name}` : 'Add my service commission'}</h2><p>Enter one claim per service item and MF case. The system checks eligibility and the imported documents, calculates the holder’s configured fee and approves qualifying commissions automatically. Removals and receipt percentage commissions are handled through document imports.</p>{error && <p role="alert" className="error-message">{error}</p>}{notice && <p role="status" className="success-message">{notice}</p>}{preferences && !allowed.length ? <p>No manual service commission items are active for this staff member. Ask the holder to enable them.</p> : <form className="form-grid" onSubmit={check}><label>Commission item<select value={form.commission_type} onChange={e => change('commission_type', e.target.value)}><option value="" disabled>Select an active item</option>{allowed.map(category => <option key={category} value={category}>{commissionLabels[category]}</option>)}</select></label><label>Service branch<select required value={form.earning_branch_id} onChange={e => change('earning_branch_id', e.target.value)}><option value="">Choose the printed branch</option>{branches.map(branch => <option key={branch.id} value={branch.id}>{branch.name}</option>)}{external.map(branch => <option key={branch.id} value={branch.id}>Outside branch: {branch.name}</option>)}</select></label><label>MF file number<input required maxLength="255" value={form.reference} onChange={e => change('reference', e.target.value)}/></label><label>Deceased name and surname<input required maxLength="255" value={form.claim_deceased} onChange={e => change('claim_deceased', e.target.value)}/></label><label>Service date<input required type="date" value={form.service_date} onChange={e => change('service_date', e.target.value)}/></label><label>Service role<select value={form.commission_role} onChange={e => change('commission_role', e.target.value)}><option value="driver">Employee</option><option value="assistant">Assistant</option></select></label><label className="full-width">Notes<textarea value={form.notes} onChange={e => change('notes', e.target.value)}/></label><button className="primary-button" disabled={busy || !allowed.includes(form.commission_type)}>Check documents and calculate</button></form>}{quote && <div className={quote.documents_valid ? 'claim-validated' : 'claim-blocked'} role="status"><strong>{money(quote.amount)}</strong><p>{quote.documents_valid ? 'Documents match and the invoice is fully paid.' : `Document uploads or corrections required: ${quote.notice}`}</p>{quote.additional_fee && <p>Additional outside-branch fee: {money(quote.additional_fee.amount)}. Added once per staff member and MF case.</p>}<button type="button" className="primary-button" disabled={busy} onClick={save}>{quote.documents_valid ? 'Save commission — approve automatically' : 'Save claim and request document uploads'}</button></div>}</section><MonthlyExpected employeeId={uid} franchiseId={franchiseId} refreshKey={refreshKey}/></section>
}
