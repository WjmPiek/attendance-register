import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'
import { commissionLabels } from './CommissionCheckboxes'

const categories = ['removals', 'invoice_commission', 'full_funeral_service', 'church_service', 'grave_service', 'cremation_service', 'joinings', 'overtime']
const money = value => `R ${Number(value || 0).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
export default function ServiceClaimPanel({ me, employee, franchiseId, onSaved }) {
  const uid = employee?.user_id || me.id
  const owner = me.roles.some(role => ['FranchiseUser', 'SuperUser'].includes(role))
  const initial = () => ({ commission_type: 'full_funeral_service', reference: '', claim_deceased: '', earning_branch_id: '', commission_role: 'driver', service_date: new Date(Date.now() + 7200000).toISOString().slice(0, 10), notes: '' })
  const [form, setForm] = useState(initial), [preferences, setPreferences] = useState(null), [external, setExternal] = useState([])
  const [quote, setQuote] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
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
      setForm(initial()); setQuote(null); await onSaved?.()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <section className="mortuary-book service-claim-panel"><section className="form-card"><h2>{owner && employee ? `Service claim for ${employee.full_name}` : 'Add my service commission'}</h2><p>Enter one claim per service item and MF case. The system checks eligibility and the imported documents, calculates the holder’s configured fee and approves qualifying commissions automatically. Enter the printed service branch and MF File number. Invoice commissions use the configured percentage before VAT where applicable. Removal claims must match the printed removal staff.</p>{error && <p role="alert" className="error-message">{error}</p>}{notice && <p role="status" className="success-message">{notice}</p>}{preferences && !allowed.length ? <p>No commission items are active for this staff member. Ask the holder to enable them.</p> : <form className="form-grid" onSubmit={check}><label>Commission item<select value={form.commission_type} onChange={e => change('commission_type', e.target.value)}><option value="" disabled>Select an active item</option>{allowed.map(category => <option key={category} value={category}>{commissionLabels[category]}</option>)}</select></label><label>Service branch<select required value={form.earning_branch_id} onChange={e => change('earning_branch_id', e.target.value)}><option value="">Choose the printed branch</option>{branches.map(branch => <option key={branch.id} value={branch.id}>{branch.name}</option>)}{external.map(branch => <option key={branch.id} value={branch.id}>Outside branch: {branch.name}</option>)}</select></label><label>MF file number<input required maxLength="255" value={form.reference} onChange={e => change('reference', e.target.value)}/></label><label>Deceased name and surname<input required maxLength="255" value={form.claim_deceased} onChange={e => change('claim_deceased', e.target.value)}/></label><label>Service date<input required type="date" value={form.service_date} onChange={e => change('service_date', e.target.value)}/></label><label>Service role<select value={form.commission_role} onChange={e => change('commission_role', e.target.value)}><option value="driver">Employee</option><option value="assistant">Assistant</option></select></label><label className="full-width">Notes<textarea value={form.notes} onChange={e => change('notes', e.target.value)}/></label><button className="primary-button" disabled={busy || !allowed.includes(form.commission_type)}>Check documents and calculate</button></form>}{quote && <div className={quote.documents_valid ? 'claim-validated' : 'claim-blocked'} role="status"><strong>{quote.estimate_available === false ? 'Amount awaiting document checks' : money(quote.amount)}</strong><p>{quote.documents_valid ? 'Documents match and the invoice is fully paid.' : `Document uploads or corrections required: ${quote.notice}`}</p>{quote.additional_fee && <p>Additional outside-branch fee: {money(quote.additional_fee.amount)}. Added once per staff member and MF case.</p>}<button type="button" className="primary-button" disabled={busy} onClick={save}>{quote.documents_valid ? 'Save commission — approve automatically' : 'Save claim and request document uploads'}</button></div>}</section></section>
}
