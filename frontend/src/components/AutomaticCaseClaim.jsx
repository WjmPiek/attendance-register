import { useEffect, useRef, useState } from 'react'
import { apiRequest } from '../api/client'
import { allowedClaimBranches } from '../utils/claim-permissions.mjs'
import { commissionLabels } from './CommissionCheckboxes'

const money = value => `R ${Number(value || 0).toLocaleString('en-ZA', { minimumFractionDigits:2, maximumFractionDigits:2 })}`

export default function AutomaticCaseClaim({ me, onSaved }) {
  const [branches,setBranches] = useState(null), [branch,setBranch] = useState(''), [reference,setReference] = useState('')
  const [busy,setBusy] = useState(false), [error,setError] = useState(''), [result,setResult] = useState(null)
  const submitting = useRef(false)
  useEffect(() => {
    let active = true
    Promise.all([apiRequest(`/receipt-commissions/options/${me.id}`),apiRequest('/receipt-commissions/external-branches')])
      .then(([preferences,outside]) => { if(active) setBranches(allowedClaimBranches(preferences,outside.branches)) })
      .catch(failure => { if(active) setError(failure.message) })
    return () => { active = false }
  },[me.id])
  const submit = async event => {
    event.preventDefault()
    if(submitting.current) return
    submitting.current = true; setBusy(true); setError(''); setResult(null)
    try {
      const data = await apiRequest('/commission/case-claim',{method:'POST',body:JSON.stringify({earning_branch_id:Number(branch),reference:reference.trim()})})
      setResult(data)
      if(data.documents_valid && data.items.every(item => item.state==='approved' || (item.state==='existing' && item.status==='approved'))) {
        const message = data.created ? `MF ${data.reference}: ${data.created} commission item(s) automatically allocated — ${money(data.total)}.` : `MF ${data.reference}: commissions are already recorded. No duplicate amounts were added.`
        await onSaved?.(message)
      }
    } catch(failure) { setError(failure.message) }
    finally { submitting.current = false; setBusy(false) }
  }
  return <section className="mortuary-book service-claim-panel"><section className="form-card">
    <h2>Claim my commissions</h2>
    <p>Select the service branch and enter the MF File Number. Your enabled commission items and amounts are checked automatically against the imported Mortuary Book, invoice and receipts.</p>
    {error && <p role="alert" className="error-message">{error}</p>}
    {!branches ? !error && <p role="status">Loading your branches…</p> : !branches.length ? <p>No commissions are enabled for you. Ask the franchise holder to check your commission settings.</p> : <form className="form-grid" onSubmit={submit}>
      <label>Service branch<select required disabled={busy} value={branch} onChange={event => {setBranch(event.target.value);setResult(null)}}><option value="">Choose the printed branch</option>{branches.map(item => <option key={item.id} value={item.id}>{item.outside?'Outside branch: ':''}{item.name}</option>)}</select></label>
      <label>MF File Number<input required disabled={busy} maxLength={255} value={reference} onChange={event => {setReference(event.target.value);setResult(null)}} /></label>
      <button type="submit" disabled={busy}>{busy?'Checking documents…':'Check and allocate commissions'}</button>
    </form>}
    {result && <div role="status" className={result.documents_valid?'claim-validated':'claim-blocked'}>
      {result.notice && <p>{result.notice} No new commission has been allocated. Retry once the documents are complete and correct.</p>}
      {result.documents_valid && <><strong>Newly allocated: {money(result.total)}</strong><ul>{result.items.map((item,index) => <li key={`${item.category}:${index}`}>{commissionLabels[item.category]}: {item.state==='approved'?money(item.amount):item.state==='existing'?`Already recorded (${item.status})`:item.notice}</li>)}</ul></>}
    </div>}
  </section></section>
}
