import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'
import './MortuaryBook.css'

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const rateLabels = { driver_in: 'Driver · business hours', driver_out: 'Driver · out of hours', assistant_in: 'Assistant · business hours', assistant_out: 'Assistant · out of hours' }
const money = value => value === null || value === undefined ? 'Rate not configured' : `R ${Number(value).toFixed(2)}`
const copy = value => JSON.parse(JSON.stringify(value))

export default function RemovalSettings({ franchiseId }) {
  const [settings, setSettings] = useState(null), [person, setPerson] = useState('0')
  const [policy, setPolicy] = useState(null), [holidays, setHolidays] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
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
    e.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      await apiRequest('/mortuary/settings', { method: 'PUT', body: JSON.stringify({
        ...policy, rates: Object.fromEntries(Object.entries(policy.rates).map(([k, v]) => [k, v === '' || v === null ? null : v])),
        extra_holidays: person === '0' ? holidays.split(/[\s,]+/).filter(Boolean) : [],
        employee_user_id: Number(person), franchise_user_id: franchiseId ? Number(franchiseId) : null,
      }) })
      const data = await load(); selectPolicy(person, data); setNotice('Removal hours and rates saved. Recalculate any open import before saving commissions.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <section className="mortuary-book">
    {error && <p role="alert" className="error-message">{error}</p>}
    {notice && <p role="status" className="success-message">{notice}</p>}
    {settings && policy && <form className="form-card" onSubmit={savePolicy}>
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
  </section>
}
