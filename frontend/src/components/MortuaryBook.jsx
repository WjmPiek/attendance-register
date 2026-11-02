import ImportBranchScope from './ImportBranchScope'
import { useEffect, useState } from 'react'
import { apiRequest, uploadMortuaryBooks } from '../api/client'
import './MortuaryBook.css'

const money = value => value === null || value === undefined ? 'Rate not configured' : `R ${Number(value).toFixed(2)}`

export default function MortuaryBook({ franchiseId }) {
  const [externalBranchId, setExternalBranchId] = useState('')
  const [settings, setSettings] = useState(null)
  const [files, setFiles] = useState([])
  const [preview, setPreview] = useState(null)
  const [allocations, setAllocations] = useState([])
  const [quote, setQuote] = useState(null)
  const [result, setResult] = useState(null)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const suffix = franchiseId ? `?franchise_user_id=${encodeURIComponent(franchiseId)}` : ''

  useEffect(() => {
    let active = true
    apiRequest(`/mortuary/settings${suffix}`).then(data => {
      if (active) setSettings(data)
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [suffix])

  const upload = async e => {
    e.preventDefault(); setBusy(true); setError(''); setNotice(''); setPreview(null); setQuote(null); setResult(null); setConfirmed(false)
    try {
      const data = await uploadMortuaryBooks(files, franchiseId, externalBranchId)
      setPreview(data); setAllocations(data.allocations)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const changeAllocation = (index, key, value) => {
    setAllocations(old => old.map((a, i) => i === index ? { ...a, [key]: key === 'employee_user_id' ? Number(value) || null : value } : a))
    setQuote(null); setConfirmed(false)
  }
  const calculate = async () => {
    setBusy(true); setError(''); setQuote(null); setConfirmed(false)
    try {
      setQuote(await apiRequest('/mortuary/quote', { method: 'POST', body: JSON.stringify({ preview_token: preview.preview_token, allocations }) }))
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const importBooks = async () => {
    setBusy(true); setError('')
    try {
      const data = await apiRequest('/mortuary/import', { method: 'POST', body: JSON.stringify({ preview_token: preview.preview_token, allocations, confirmed_franchise: confirmed, quote_token: quote.quote_token }) })
      setResult(data); setPreview(null); setQuote(null); setFiles([])
    } catch (e) { setError(e.message); setQuote(null); setConfirmed(false) } finally { setBusy(false) }
  }
  const totals = quote ? Object.values(quote.items.reduce((acc, item) => {
    if (item.duplicate) return acc
    const group = acc[item.employee_user_id] ||= { name: item.employee_name, quantity: 0, total: 0, missing: false }
    group.quantity++; group.total += Number(item.amount || 0); group.missing ||= item.amount === null
    return acc
  }, {})) : []

  return <section className="mortuary-book">
    <ImportBranchScope franchiseId={franchiseId} value={externalBranchId} onChange={value => { setExternalBranchId(value); setPreview(null) }}/>
    <div className="form-card">
      <h2>Mortuary Book</h2>
      <p>Import removal commissions from printed Mortuary Book PDFs. Review the employees, roles and fees before saving to their Work Hubs.</p>
      <p className="muted">Service date uses Date Generated. Fee classification uses Date In and Time In, in South African local time. Working hours come from the staff register. Sundays and public holidays use their separate removal fee when configured. End times are exclusive: 17:00 is out of hours when a shift ends at 17:00.</p>
    </div>
    {error && <div role="alert" className="error-message">{error}</div>}
    {notice && <div role="status" className="success-message">{notice}</div>}
    {settings && <form className="form-card" onSubmit={upload}>
      <h3>1. Select Mortuary Books</h3>
      <label>PDF files<input type="file" accept="application/pdf,.pdf" multiple required disabled={busy} onChange={e => { setFiles(Array.from(e.target.files)); setPreview(null); setQuote(null); setResult(null) }}/></label>
      <p className="muted">Select up to 30 files (10 MB per file, 50 MB per batch). Original text PDFs are supported; scanned images need a searchable PDF first.</p>
      <button className="primary-button" disabled={busy || !files.length}>{busy ? 'Working…' : 'Read books and match staff'}</button>
    </form>}
    {preview && <div className="form-card">
      <h3>2. Review records and staff</h3>
      {preview.errors.length > 0 && <div className="error-message"><strong>These pages will not be imported:</strong><ul>{preview.errors.map((e, i) => <li key={i}>{e.filename}{e.page ? ` · page ${e.page}` : ''}: {e.error}</li>)}</ul></div>}
      {preview.records.map((r, i) => <article className="mortuary-record" key={i}>
        <h4>MF {r.reference} · {r.branch}</h4>
        <dl><div><dt>Service date</dt><dd>{r.service_date}</dd></div><div><dt>Date / Time In</dt><dd>{r.date_in} · {r.time_in}</dd></div><div><dt>Deceased</dt><dd>{r.deceased || 'Not provided'}</dd></div><div><dt>ID Number</dt><dd>{r.id_number || 'Not provided'}</dd></div><div><dt>Collected at</dt><dd>{r.collected_at || 'Not provided'}</dd></div><div><dt>Driver In</dt><dd>{r.driver_in}</dd></div></dl>
        <p className="muted">{r.filename} · page {r.page}. Check roles before calculating, especially when two names are listed.</p>
        {allocations.map((a, n) => a.record !== i ? null : <div className="mortuary-allocation" key={n}>
          <strong>{r.names[a.name_index]}</strong>
          <label>Employee<select required value={a.employee_user_id || ''} disabled={busy} onChange={e => changeAllocation(n, 'employee_user_id', e.target.value)}><option value="">Select employee — no unique match</option>{settings.employees.map(p => <option key={p.user_id} value={p.user_id}>{p.full_name}{p.employee_number ? ` · ${p.employee_number}` : ''}</option>)}</select></label>
          <label>Removal role<select value={a.role} disabled={busy} onChange={e => changeAllocation(n, 'role', e.target.value)}><option value="driver">Employee</option><option value="assistant">Assistant</option></select></label>
        </div>)}
      </article>)}
      <button type="button" className="primary-button" disabled={busy || !allocations.length || allocations.some(a => !a.employee_user_id)} onClick={calculate}>Calculate commissions</button>
    </div>}
    {quote && <div className="form-card">
      <h3>3. Save Mortuary Book evidence</h3>
      <div className="table-wrap"><table><thead><tr><th>MF / Branch</th><th>Employee</th><th>Role / Fee</th><th>Quantity</th><th>Amount</th></tr></thead><tbody>{quote.items.map((r, i) => <tr key={i}><td>{r.record_data.reference}<br/>{r.record_data.branch}</td><td>{r.employee_name}</td><td>{r.role === 'driver' ? 'Employee' : 'Assistant'} · {r.fee_label || (r.band === 'in' ? 'Business hours' : 'After hours')}{Number(r.additional_fee) > 0 && <small className="commission-branch-summary">Base: {money(r.removal_base_fee)} + Other branch: {money(r.additional_fee)}</small>}</td><td>{r.duplicate ? 'Already recorded — skipped' : '1'}</td><td>{r.duplicate ? 'Skipped' : money(r.amount)}</td></tr>)}</tbody></table></div>
      <h4>Indicative fees per employee</h4>
      <div className="mortuary-rates">{totals.map(r => <div className="mortuary-total" key={r.name}><strong>{r.name}</strong><span>{r.quantity} removal(s)</span><strong>{r.missing ? 'Configure missing fees' : money(r.total)}</strong></div>)}</div>
      <p><strong>Indicative removal fees: {money(quote.total)}</strong></p><p>No commission is earned by saving a book. A matching MF Invoice, receipts covering the full invoice, and an enabled employee category are required.</p>
      {quote.items.some(r => !r.duplicate && r.amount === null) && <p className="error-message">Fees can be configured before approving matched commissions. Saving a book does not earn commission.</p>}
      <label className="mortuary-confirm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} disabled={busy}/>I confirm every book belongs to this franchise, the staff and roles are correct, and the books should be saved for matching with MF File Receipts.{preview.errors.length > 0 ? ' I have reviewed the pages that will be excluded.' : ''}</label>
      <button type="button" className="primary-button" disabled={busy || !confirmed} onClick={importBooks}>Save books for matching</button>
    </div>}
    {result && <div className="form-card" role="status"><h3>Import complete</h3><p>{result.saved_books || 0} books saved. {result.skipped_duplicates} duplicate books skipped.</p><p>{result.message}</p>{Object.entries(result.totals).map(([uid, r]) => <p key={uid}><strong>{r.employee_name}</strong>: {r.quantity} removal(s) · {money(r.total)}</p>)}<p>Open HR Staff → Upload proof → MF File Receipt to import receipts and review matched commissions.</p></div>}
  </section>
}
