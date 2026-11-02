import { useEffect, useState } from 'react'
import { apiRequest, uploadMortuaryBooks } from '../api/client'
import './MortuaryBook.css'

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const rateLabels = { driver_in: 'Driver · business hours', driver_out: 'Driver · out of hours', assistant_in: 'Assistant · business hours', assistant_out: 'Assistant · out of hours' }
const money = value => value === null || value === undefined ? 'Rate not configured' : `R ${Number(value).toFixed(2)}`
const copy = value => JSON.parse(JSON.stringify(value))

export default function MortuaryBook({ franchiseId, canManage = true }) {
  const [settings, setSettings] = useState(null)
  const [person, setPerson] = useState('0')
  const [policy, setPolicy] = useState(null)
  const [holidays, setHolidays] = useState('')
  const [files, setFiles] = useState([])
  const [preview, setPreview] = useState(null)
  const [allocations, setAllocations] = useState([])
  const [quote, setQuote] = useState(null)
  const [result, setResult] = useState(null)
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [showSettings, setShowSettings] = useState(false)
  const suffix = franchiseId ? `?franchise_user_id=${encodeURIComponent(franchiseId)}` : ''

  const load = async () => {
    const data = await apiRequest(`/mortuary/settings${suffix}`)
    setSettings(data)
    return data
  }
  useEffect(() => {
    let active = true
    apiRequest(`/mortuary/settings${suffix}`).then(data => {
      if (active) { setSettings(data); setPolicy(copy(data.default)); setHolidays(data.default.extra_holidays.join('\n')) }
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [suffix])

  const selectPolicy = (id, data = settings) => {
    setPerson(String(id))
    const saved = data.overrides[String(id)]
    const next = copy(saved || data.default)
    if (String(id) !== '0' && !saved) next.rates = Object.fromEntries(Object.keys(rateLabels).map(k => [k, null]))
    if (String(id) !== '0') next.extra_holidays = []
    setPolicy(next)
    setHolidays((next.extra_holidays || []).join('\n'))
  }
  const savePolicy = async e => {
    e.preventDefault(); setBusy(true); setError(''); setNotice(''); setQuote(null)
    try {
      await apiRequest('/mortuary/settings', { method: 'PUT', body: JSON.stringify({
        ...policy, rates: Object.fromEntries(Object.entries(policy.rates).map(([k, v]) => [k, v === '' || v === null ? null : v])),
        extra_holidays: person === '0' ? holidays.split(/[\s,]+/).filter(Boolean) : [],
        employee_user_id: Number(person), franchise_user_id: franchiseId ? Number(franchiseId) : null,
      }) })
      const data = await load(); selectPolicy(person, data); setNotice('Removal hours and rates saved. Recalculate any open import before saving commissions.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const upload = async e => {
    e.preventDefault(); setBusy(true); setError(''); setNotice(''); setPreview(null); setQuote(null); setResult(null); setConfirmed(false)
    try {
      const data = await uploadMortuaryBooks(files, franchiseId)
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
    <div className="form-card">
      <h2>Mortuary Book</h2>
      <p>Import removal commissions from printed Mortuary Book PDFs. Review the employees, roles and fees before saving to their Work Hubs.</p>
      <p className="muted">Service date uses Date Generated. Fee classification uses Date In and Time In, in South African local time. Sundays and public holidays always use out-of-hours fees. End times are exclusive: 17:00 is out of hours when a shift ends at 17:00.</p>
      {canManage && <button type="button" className="glass-button" onClick={() => setShowSettings(v => !v)}>{showSettings ? 'Hide hours and rates' : 'Configure hours and removal rates'}</button>}
    </div>
    {error && <div role="alert" className="error-message">{error}</div>}
    {notice && <div role="status" className="success-message">{notice}</div>}
    {showSettings && settings && policy && <form className="form-card" onSubmit={savePolicy}>
      <h3>Business hours and removal fees</h3>
      <label>Settings for<select value={person} disabled={busy} onChange={e => selectPolicy(e.target.value)}>
        <option value="0">Franchise defaults</option>
        {settings.employees.map(e => <option key={e.user_id} value={e.user_id}>{e.full_name}</option>)}
      </select></label>
      <p className="muted">Employee-specific hours apply to removal commissions. Leave employee rates blank to use franchise defaults. Driver and assistant fees are paid separately; the fee is never split between staff.</p>
      <div className="mortuary-week">{days.map((day, i) => <div className="mortuary-day" key={day}>
        <label><input type="checkbox" checked={policy.week[i] !== null} onChange={e => setPolicy(p => ({ ...p, week: p.week.map((w, n) => n === i ? e.target.checked ? { start: '08:00', end: i === 5 ? '13:00' : '17:00' } : null : w) }))}/>{day}</label>
        <label>Start<input aria-label={`${day} start`} type="time" required disabled={!policy.week[i]} value={policy.week[i]?.start || ''} onChange={e => setPolicy(p => ({ ...p, week: p.week.map((w, n) => n === i ? { ...w, start: e.target.value } : w) }))}/></label>
        <label>End<input aria-label={`${day} end`} type="time" required disabled={!policy.week[i]} value={policy.week[i]?.end || ''} onChange={e => setPolicy(p => ({ ...p, week: p.week.map((w, n) => n === i ? { ...w, end: e.target.value } : w) }))}/></label>
      </div>)}</div>
      <div className="mortuary-rates">{Object.entries(rateLabels).map(([key, label]) => <label key={key}>{label} (R)<input type="number" min="0" max="1000000" step="0.01" placeholder={person === '0' ? 'Enter fee' : 'Use franchise default'} value={policy.rates[key] ?? ''} onChange={e => setPolicy(p => ({ ...p, rates: { ...p.rates, [key]: e.target.value } }))}/></label>)}</div>
      {person === '0' && <label>Additional proclaimed public holidays (YYYY-MM-DD, one per line)<textarea value={holidays} onChange={e => setHolidays(e.target.value)} placeholder="YYYY-MM-DD"/></label>}
      <button className="primary-button" disabled={busy}>Save hours and rates</button>
    </form>}
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
          <label>Removal role<select value={a.role} disabled={busy} onChange={e => changeAllocation(n, 'role', e.target.value)}><option value="driver">Driver</option><option value="assistant">Assistant</option></select></label>
        </div>)}
      </article>)}
      <button type="button" className="primary-button" disabled={busy || !allocations.length || allocations.some(a => !a.employee_user_id)} onClick={calculate}>Calculate commissions</button>
    </div>}
    {quote && <div className="form-card">
      <h3>3. Save Mortuary Book evidence</h3>
      <div className="table-wrap"><table><thead><tr><th>MF / Branch</th><th>Employee</th><th>Role / Fee</th><th>Quantity</th><th>Amount</th></tr></thead><tbody>{quote.items.map((r, i) => <tr key={i}><td>{r.record_data.reference}<br/>{r.record_data.branch}</td><td>{r.employee_name}</td><td>{r.role} · {r.band === 'in' ? 'Business hours' : 'Out of hours'}</td><td>{r.duplicate ? 'Already recorded — skipped' : '1'}</td><td>{r.duplicate ? 'Skipped' : money(r.amount)}</td></tr>)}</tbody></table></div>
      <h4>Indicative fees per employee</h4>
      <div className="mortuary-rates">{totals.map(r => <div className="mortuary-total" key={r.name}><strong>{r.name}</strong><span>{r.quantity} removal(s)</span><strong>{r.missing ? 'Configure missing fees' : money(r.total)}</strong></div>)}</div>
      <p><strong>Indicative removal fees: {money(quote.total)}</strong></p><p>No commission is earned by saving a book. A matching MF File Receipt and an enabled employee category are both required.</p>
      {quote.items.some(r => !r.duplicate && r.amount === null) && <p className="error-message">Fees can be configured before approving matched commissions. Saving a book does not earn commission.</p>}
      <label className="mortuary-confirm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} disabled={busy}/>I confirm every book belongs to this franchise, the staff and roles are correct, and the books should be saved for matching with MF File Receipts.{preview.errors.length > 0 ? ' I have reviewed the pages that will be excluded.' : ''}</label>
      <button type="button" className="primary-button" disabled={busy || !confirmed} onClick={importBooks}>Save books for matching</button>
    </div>}
    {result && <div className="form-card" role="status"><h3>Import complete</h3><p>{result.saved_books || 0} books saved. {result.skipped_duplicates} duplicate books skipped.</p><p>{result.message}</p>{Object.entries(result.totals).map(([uid, r]) => <p key={uid}><strong>{r.employee_name}</strong>: {r.quantity} removal(s) · {money(r.total)}</p>)}<p>Open HR Staff → MF File Receipt to import receipts and review matched commissions.</p></div>}
  </section>
}
