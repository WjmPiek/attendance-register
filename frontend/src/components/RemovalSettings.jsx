import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'
import './MortuaryBook.css'

const feeRows = [
  { label: 'Removal during business hours', employee: 'driver_in', assistant: 'assistant_in' },
  { label: 'After-hours removal', employee: 'driver_out', assistant: 'assistant_out' },
  { label: 'Sunday / public holiday removal', employee: 'driver_sunday_holiday', assistant: 'assistant_sunday_holiday' },
  { label: 'Service for Other Branch (additional fee)', employee: 'driver_other_branch', assistant: 'assistant_other_branch' },
]
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
    if (String(id) !== '0' && !saved) next.rates = Object.fromEntries(feeRows.flatMap(row => [[row.employee, null], [row.assistant, null]]))
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
      const data = await load(); selectPolicy(person, data); setNotice('Removal fees saved. Recalculate any open import before saving commissions.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <section className="mortuary-book">
    {error && <p role="alert" className="error-message">{error}</p>}
    {notice && <p role="status" className="success-message">{notice}</p>}
    {settings && policy && <form className="removal-settings-form" onSubmit={savePolicy}>
      <section className="form-card">
      <label>Settings for<select value={person} disabled={busy} onChange={e => selectPolicy(e.target.value)}>
        <option value="0">Franchise defaults</option>
        {settings.employees.map(e => <option key={e.user_id} value={e.user_id}>{e.full_name}</option>)}
      </select></label>
      <p className="muted">Working hours come from each manager or employee’s Add/Edit Staff record. Employee-specific fees apply to removal commissions. Leave fees blank to use franchise defaults. Employee and Assistant fees are paid separately.</p>
      </section>
      <section className="form-card">
      <h3>Removal commissions</h3>
      <p className="muted">Amounts in rand. Sunday / public holiday rates take priority over ordinary after-hours rates. If no separate Sunday rate is configured, the after-hours rate applies. Service for Other Branch is added once when the employee’s home branch differs from the service branch. Blank additional fees default to zero, or inherit the franchise setting for an employee.</p>
      <div className="table-wrap"><table className="removal-fee-table"><thead><tr><th>Commission category</th><th>Employee</th><th>Assistant</th></tr></thead><tbody>{feeRows.map(row => <tr key={row.employee}><th scope="row">{row.label}</th>{['employee', 'assistant'].map(role => { const key = row[role]; return <td key={key}><input aria-label={`${row.label} · ${role === 'employee' ? 'Employee' : 'Assistant'}`} type="number" min="0" max="1000000" step="0.01" placeholder={person === '0' ? 'Enter fee' : 'Use franchise default'} value={policy.rates[key] ?? ''} onChange={e => setPolicy(p => ({ ...p, rates: { ...p.rates, [key]: e.target.value } }))}/></td> })}</tr>)}</tbody></table></div>
      {person === '0' && <label>Additional proclaimed public holidays (YYYY-MM-DD, one per line)<textarea value={holidays} onChange={e => setHolidays(e.target.value)} placeholder="YYYY-MM-DD"/></label>}
      <button className="primary-button" disabled={busy}>Save removal fees</button>
      </section>
    </form>}
  </section>
}
