import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'
import { commissionLabels } from './CommissionCheckboxes'
import { allowedClaimTypes, allowedClaimBranches } from '../utils/claim-permissions.mjs'
import AutomaticCaseClaim from './AutomaticCaseClaim'

const money = value => `R ${Number(value || 0).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
export default function ServiceClaimPanel(props) {
  return props.simple ? <AutomaticCaseClaim me={props.me} onSaved={props.onSaved} /> : <ManualServiceClaimPanel {...props} />
}

function ManualServiceClaimPanel({ me, employee, franchiseId, onSaved, simple = false }) {
  const uid = employee?.user_id || me.id
  const owner = me.roles.some(role => ['FranchiseUser', 'SuperUser'].includes(role))
  const initial = () => ({ commission_type: '', reference: '', claim_deceased: '', earning_branch_id: '', commission_role: 'driver', service_date: new Date(Date.now() + 7200000).toISOString().slice(0, 10), notes: '' })
  const [form, setForm] = useState(initial), [preferences, setPreferences] = useState(null), [external, setExternal] = useState([])
  const [quote, setQuote] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  useEffect(() => {
    let active = true
    setPreferences(null); setQuote(null); setForm(initial()); setError('')
    const suffix = franchiseId ? `?franchise_user_id=${franchiseId}` : ''
    Promise.all([apiRequest(`/receipt-commissions/options/${uid}`), apiRequest(`/receipt-commissions/external-branches${suffix}`)]).then(([options, outside]) => { if (active) { setPreferences(options); setExternal(outside.branches) } }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [uid, franchiseId])
  const branches = allowedClaimBranches(preferences, external)
  const allowed = allowedClaimTypes(preferences, form.earning_branch_id, external)
  const allowedKey = allowed.join('|')
  useEffect(() => {
    setForm(old => {
      const category = allowed.includes(old.commission_type) ? old.commission_type : allowed.length === 1 ? allowed[0] : ''
      return category === old.commission_type ? old : { ...old, commission_type: category }
    })
    setQuote(null)
  }, [allowedKey, form.earning_branch_id])
  const change = (field, value) => { setForm(old => ({ ...old, [field]: value, ...(field === 'earning_branch_id' ? { commission_type: '' } : {}) })); setQuote(null); setNotice('') }
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
  const showFields = Boolean(form.earning_branch_id && allowed.includes(form.commission_type))
  return <section className="mortuary-book service-claim-panel"><section className="form-card">
    <h2>{owner && employee ? `Service claim for ${employee.full_name}` : 'Add my service commission'}</h2>
    {!simple && <p>Choose the service branch. Only commission items enabled for this staff member at that branch are available. Amounts are calculated from the configured rates.</p>}
    {error && <p role="alert" className="error-message">{error}</p>}{notice && <p role="status" className="success-message">{notice}</p>}
    {!preferences ? !error && <p role="status">Loading enabled commission items…</p> : !branches.length ? <p>No claimable commission items are enabled for this staff member. Ask the franchise holder to configure their commission permissions. Any outside-branch additional fee is added automatically to an eligible service.</p> : <form className="form-grid" onSubmit={simple ? event => { event.preventDefault(); save() } : check}>
      <label>Service branch<select disabled={busy} required value={form.earning_branch_id} onChange={e => change('earning_branch_id', e.target.value)}><option value="">Choose the printed branch</option>{branches.map(branch => <option key={branch.id} value={branch.id}>{branch.outside ? 'Outside branch: ' : ''}{branch.name}</option>)}</select></label>
      {form.earning_branch_id && <label>Commission item<select disabled={busy} required value={form.commission_type} onChange={e => change('commission_type', e.target.value)}><option value="" disabled>Select an enabled item</option>{allowed.map(category => <option key={category} value={category}>{commissionLabels[category]}</option>)}</select></label>}
      {showFields && <>
        {!simple && <p className="full-width muted">{form.commission_type === 'invoice_commission' ? 'The configured percentage is calculated from the invoice, excluding VAT for a VAT-registered branch. All matching payment evidence is required.' : form.commission_type === 'removals' ? 'The claim must match the printed removal staff and role. The employee’s working hours and the removal date/time determine the configured fee.' : 'One configured fixed fee applies per qualifying MF File and service item.'}</p>}
        <label>MF file number<input disabled={busy} required maxLength="255" value={form.reference} onChange={e => change('reference', e.target.value)}/></label>
        <label>Deceased name and surname<input disabled={busy} required maxLength="255" value={form.claim_deceased} onChange={e => change('claim_deceased', e.target.value)}/></label>
        <label>Service date<input disabled={busy} required type="date" value={form.service_date} onChange={e => change('service_date', e.target.value)}/></label>
        <label>Service role<select disabled={busy} value={form.commission_role} onChange={e => change('commission_role', e.target.value)}><option value="driver">Employee</option><option value="assistant">Assistant</option></select></label>
        {!simple && <label className="full-width">Notes<textarea disabled={busy} value={form.notes} onChange={e => change('notes', e.target.value)}/></label>}
        <button className="primary-button" disabled={busy}>{simple ? 'Submit' : 'Check documents and calculate'}</button>
      </>}
    </form>}
    {!simple && showFields && quote && <div className={quote.documents_valid ? 'claim-validated' : 'claim-blocked'} role="status"><strong>{quote.estimate_available === false ? 'Amount awaiting document checks' : money(quote.amount)}</strong><p>{quote.documents_valid ? 'Documents match and the invoice is fully paid.' : `Document uploads or corrections required: ${quote.notice}`}</p>{quote.additional_fee && <p>Additional outside-branch fee: {money(quote.additional_fee.amount)}. Added once per staff member and MF case.</p>}<button type="button" className="primary-button" disabled={busy} onClick={save}>{quote.documents_valid ? 'Save commission — approve automatically' : 'Save claim and request document uploads'}</button></div>}
  </section></section>
}
