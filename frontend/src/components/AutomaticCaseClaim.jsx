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
    } catch(failure) { setError(failure.message) }
    finally { submitting.current = false; setBusy(false) }
  }
  return <section className="mortuary-book service-claim-panel"><section className="form-card">
    <h2>Claim my commissions</h2>
    <p>Select the Mortuary Book branch and enter the MF File Number. Your enabled commissions are saved under Waiting to be finalised, even before documents are uploaded. Amounts move to Approved only after finalisation.</p>
    {error && <p role="alert" className="error-message">{error}</p>}
    {!branches ? !error && <p role="status">Loading your branches…</p> : !branches.length ? <p>No commissions are enabled for you. Ask the franchise holder to check your commission settings.</p> : <form className="form-grid" onSubmit={submit}>
      <label>Service branch<select required disabled={busy} value={branch} onChange={event => {setBranch(event.target.value);setResult(null)}}><option value="">Choose the printed branch</option>{branches.map(item => <option key={item.id} value={item.id}>{item.outside?'Outside branch: ':''}{item.name}</option>)}</select></label>
      <label>MF File Number<input required disabled={busy} maxLength={255} value={reference} onChange={event => {setReference(event.target.value);setResult(null)}} /></label>
      <button type="submit" disabled={busy}>{busy?'Saving claim…':'Submit MF claim'}</button>
    </form>}
    {result && <div role="status" className="claim-blocked">
      <strong>Mortuary Book branch: {result.branch_name || branches?.find(item=>String(item.id)===branch)?.name}</strong>
      {result.notice && <p>{result.notice}</p>}
      <strong>MF commission total: {money(result.total)}</strong>
      <p>Approved: {money(result.approved_total || 0)} · Waiting to be finalised: {money(result.waiting_total ?? result.total)}</p>
      <p>Amounts shown are estimates until documents and rates are finalised. Items awaiting calculation are not included in this subtotal.</p>
      <ul>{result.items.map((item,index) => <li key={`${item.category}:${index}`}>{commissionLabels[item.category]}: {item.state==='existing'?`Already recorded (${item.status}) — ${money(item.amount)}`:item.estimate_available===false?'Waiting for documents to calculate':`${money(item.amount)} · Waiting to be finalised`}{item.notice && <p>{item.notice}</p>}</li>)}</ul>
      <button type="button" onClick={()=>onSaved?.(result.created?`MF ${result.reference}: claims saved under Waiting to be finalised.`:`MF ${result.reference}: commissions already recorded; no duplicate claims added.`)}>Done</button>
    </div>}
  </section></section>
}
