import { useEffect, useState } from 'react'
import { getCommissionEntries, apiRequest } from '../api/client'
import { commissionLabels } from './CommissionCheckboxes'

const money = n => `R ${Number(n || 0).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const source = row => { try { return JSON.parse(row.source_metadata || '{}') } catch { return {} } }
export default function MonthlyCommissionStatement({ employeeUserId, franchiseId, earningBranchId }) {
  const [month, setMonth] = useState(new Date(Date.now() + 7200000).toISOString().slice(0, 7))
  const [items, setItems] = useState([]), [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [branches,setBranches] = useState([]), [branch,setBranch] = useState('')
  useEffect(() => {let active=true;apiRequest(`/receipt-commissions/options/${employeeUserId}`).then(d=>{if(active)setBranches(d.branches||[])}).catch(()=>{});return()=>{active=false}},[employeeUserId])
  useEffect(() => {
    if (!/^\d{4}-\d{2}$/.test(month)) return
    const [y, m] = month.split('-').map(Number)
    const end = new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10)
    let active = true
    setItems([]); setError(''); setLoading(true)
    getCommissionEntries({ employeeUserId, earningBranchId: earningBranchId || branch, franchiseUserId: franchiseId || '', fromDate: `${month}-01`, toDate: end, status: 'approved' })
      .then(data => { if (active) { setItems(data.items || []); setLoading(false) } }).catch(e => { if (active) { setItems([]); setError(e.message); setLoading(false) } })
    return () => { active = false }
  }, [employeeUserId, franchiseId, month, earningBranchId, branch])
  return <section className="monthly-commission-statement">
    <h3>Monthly commission statement</h3><label>Month<input type="month" value={month} onChange={e => setMonth(e.target.value)}/></label>
    {!earningBranchId && <label>Commission branch<select value={branch} onChange={e=>setBranch(e.target.value)}><option value="">All linked branches</option>{branches.map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select></label>}
    <p className="muted">Approved commissions only, grouped by category using their service dates. Waiting or unmatched documents do not contribute to earnings.</p>
    {error && <p role="alert" className="error-message">{error}</p>}
    {Object.entries(commissionLabels).map(([category, label]) => {
      const rows = items.filter(r => r.commission_type === category)
      if (!rows.length) return null
      const subtotal = rows.reduce((n, r) => n + Number(r.calculated_amount), 0)
      return <section className="mortuary-record" key={category}><h4>{label}</h4><div className="table-wrap"><table><thead><tr><th>Date / MF / Branch</th><th>Deceased / ID</th><th>Commissionable amount</th><th>Fee / Rate</th><th>Commission</th></tr></thead><tbody>{rows.map(r => { const meta = source(r); return <tr key={r.id}><td>{r.service_date}<br/>{r.reference}<br/>{r.branch_name}</td><td>{meta.deceased || '—'}<br/>{meta.id_number || '—'}</td><td>{r.invoice_value_before_tax == null ? '—' : money(r.invoice_value_before_tax)}{meta.vat_registered === false && <small> · Not VAT registered</small>}</td><td>{category === 'invoice_commission' ? `${r.applied_rate}%` : category === 'overtime' ? `${r.applied_rate}×` : money(r.applied_rate)}</td><td>{money(r.calculated_amount)}</td></tr> })}</tbody></table></div><strong>{label} subtotal: {money(subtotal)}</strong></section>
    })}
    {!loading && !error && !items.length && <p>No approved commissions for this month.</p>}
    <strong>Monthly total: {loading ? 'Loading…' : error ? 'Unavailable' : money(items.reduce((n, r) => n + Number(r.calculated_amount), 0))}</strong>
  </section>
}
