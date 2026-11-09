import { useEffect, useState } from 'react'
import { apiRequest, getCommissionStructures } from '../api/client'
import { getStaffBranchId } from '../api/branchContext'
import './MortuaryBook.css'

const feeRows = [
  { label: 'Removal during business hours', employee: 'driver_in', assistant: 'assistant_in' },
  { label: 'After-hours removal', employee: 'driver_out', assistant: 'assistant_out' },
  { label: 'Sunday / public holiday removal', employee: 'driver_sunday_holiday', assistant: 'assistant_sunday_holiday' },
  { label: 'Service for Other Branch (additional fee)', employee: 'driver_other_branch', assistant: 'assistant_other_branch' },
  ...[['grave_service','Grave Service'],['full_funeral_service','Full Funeral Service'],['cremation_service','Cremation Service'],['church_service','Church Service'],['joinings','Joinings'],['overtime','Overtime (fixed amount per approved claim)'],['invoice_commission','MF File Receipt (% of invoice amount before VAT where applicable)']].map(([type,label]) => ({type,label,employee:`driver_${type}`,assistant:`assistant_${type}`,percentage:type==='invoice_commission'})),
]
const copy = value => JSON.parse(JSON.stringify(value))

export default function RemovalSettings({ franchiseId }) {
  const [settings, setSettings] = useState(null), [person, setPerson] = useState('0')
  const [branch,setBranch]=useState(()=>String(getStaffBranchId() || ''))
  const [policy, setPolicy] = useState(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const suffix = franchiseId ? `?franchise_user_id=${encodeURIComponent(franchiseId)}` : ''
  const branchSuffix=suffix+(branch?`${suffix?'&':'?'}branch_id=${encodeURIComponent(branch)}`:'')
  const load = async () => {
    const [data, structures, receipt] = await Promise.all([apiRequest(`/mortuary/settings${branchSuffix}`), getCommissionStructures(franchiseId), apiRequest(`/receipt-commissions/settings${suffix}`)])
    if(branch&&Number(data.branch_id)!==Number(branch))throw new Error('Branch fee settings are updating. Refresh this page shortly before saving branch fees.')
    for (const row of feeRows.filter(row => row.type)) {
      const old = row.percentage ? receipt.settings.receipt_percentage : row.type !== 'overtime' ? structures.find(s => s.commission_type === row.type && s.is_active)?.rate : null
      if (old != null && (row.percentage || Number(old) > 0)) for (const key of [row.employee,row.assistant]) if (data.default.rates[key] == null) data.default.rates[key] = old
    }
    return data
  }
  useEffect(() => {
    let active=true
    setSettings(null);setPolicy(null);setPerson('0');setNotice('');setError('')
    load().then(data=>{if(active){setSettings(data);setPolicy({...copy(data.default),...(branch?{rates:copy(data.branch_rates || {})}:{})})}})
      .catch(e=>{if(active){setError(e.message);if(branch&&e.status===403)setBranch('')}})
    return()=>{active=false}
  }, [branchSuffix])

  const selectPolicy = (id, data = settings) => {
    setPerson(String(id))
    const saved = data.overrides[String(id)]
    const next = branch?{...copy(data.default),rates:copy(data.branch_rates || {})}:copy(saved || data.default)
    if (String(id) !== '0' && !saved) next.rates = Object.fromEntries(feeRows.flatMap(row => [[row.employee, null], [row.assistant, null]]))
    if (String(id) !== '0') next.extra_holidays = []
    setPolicy(next)
  }
  const savePolicy = async e => {
    e.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      await apiRequest('/mortuary/settings', { method: 'PUT', body: JSON.stringify({
        ...policy, rates: Object.fromEntries(Object.entries(policy.rates).map(([k, v]) => [k, v === '' || v === null ? null : v])),
        extra_holidays: [],
        employee_user_id: Number(person), franchise_user_id: franchiseId ? Number(franchiseId) : null,
        branch_id:branch?Number(branch):null,
      }) })
      const data = await load();setSettings(data);selectPolicy(person, data); setNotice(branch?'Fees saved for this branch only. Other branches keep their own fees.':'Main commission defaults saved. Branch-specific fees remain unchanged.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <section className="mortuary-book">
    <section className="form-card"><label>Commission branch<select value={branch} disabled={busy} onChange={e=>setBranch(e.target.value)}><option value="">Main defaults for linked branches</option>{settings?.branches?.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <p className="muted">Each claim uses the earning branch’s fees. A blank branch fee uses the main default. Staff permissions are checked separately, and individual staff branch fees take priority.</p>
    </section>
    {error && <p role="alert" className="error-message">{error}</p>}
    {notice && <p role="status" className="success-message">{notice}</p>}
    {settings && policy && <form className="removal-settings-form" onSubmit={savePolicy}>
      <section className="form-card">
      <label>Settings for<select value={person} disabled={busy} onChange={e => selectPolicy(e.target.value)}>
        <option value="0">{branch?'Branch defaults':'Main defaults'}</option>
        {!branch&&settings.employees.map(e => <option key={e.user_id} value={e.user_id}>{e.full_name}</option>)}
      </select></label>
      <p className="muted">Working hours come from each manager or employee’s Add/Edit Staff record. Set individual staff branch fees under that person’s branch commission permissions. Employee and Assistant fees are paid separately.</p>
      </section>
      <section className="form-card">
      <h3>Commissions</h3>
      <p className="muted">Service fees are fixed rand amounts per matched MF case. MF File Receipt is a percentage. Overtime is a fixed fee per approved claim. Sunday / public holiday rates take priority over ordinary after-hours rates. If no separate Sunday rate is configured, the after-hours rate applies. Service for Other Branch applies only to a branch outside the holder’s linked group. Blank additional fees default to zero, or inherit the franchise setting for an employee.</p>
      <div className="table-wrap"><table className="removal-fee-table"><thead><tr><th>Commission category</th><th>Employee</th><th>Assistant</th></tr></thead><tbody>{feeRows.map(row => <tr key={row.employee}><th scope="row">{row.label}</th>{['employee', 'assistant'].map(role => { const key = row[role]; return <td key={key}><input aria-label={`${row.label} · ${role === 'employee' ? 'Employee' : 'Assistant'}`} type="number" min="0" max={row.percentage ? 100 : 1000000} step={row.percentage ? "0.0001" : "0.01"} placeholder={branch?`Main default: ${settings.main_default?.rates[key] ?? 'not configured'}`:person === '0' ? 'Enter fee' : 'Use main default'} value={policy.rates[key] ?? ''} onChange={e => setPolicy(p => ({ ...p, rates: { ...p.rates, [key]: e.target.value } }))}/></td> })}</tr>)}</tbody></table></div>
      <button className="primary-button" disabled={busy}>Save commissions</button>
      </section>
    </form>}
  </section>
}
