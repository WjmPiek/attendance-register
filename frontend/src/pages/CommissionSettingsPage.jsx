import { useEffect, useState } from 'react'
import RemovalSettings from '../components/RemovalSettings'
import ReceiptSettings from '../components/ReceiptSettings'
import { getCommissionStructures, saveCommissionStructure } from '../api/client'

function OtherCommissionSettings() {
  const [structures, setStructures] = useState([])
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(null)
  const load = async () => {
    const rows = (await getCommissionStructures()).filter(s => !['removals', 'invoice_commission'].includes(s.commission_type))
    setStructures(rows)
  }
  useEffect(() => { load().catch(e => setError(e.message)) }, [])
  const update = (id, values) => { setStructures(rows => rows.map(row => row.id === id ? { ...row, ...values } : row)); setNotice('') }
  const save = async form => {
    setBusy(form.id); setError(''); setNotice('')
    try {
      await saveCommissionStructure({ ...form, rate: Number(form.rate), overtime_multiplier: form.calculation_type === 'overtime' ? Number(form.overtime_multiplier ?? 1) : null })
      setNotice(`${form.label} rate saved.`)
    } catch (e) { setError(e.message) } finally { setBusy(null) }
  }
  return <section className="form-card">
    <h2>Commission Rates</h2>
    <p className="muted">All service commission items are listed below. Overtime uses hours × hourly rate × multiplier.</p>
    {error && <p role="alert" className="error-message">{error}</p>}{notice && <p role="status" className="success-message">{notice}</p>}
    <div className="commission-rate-list">{structures.map(form => <form className="commission-rate-row" key={form.id} onSubmit={event => { event.preventDefault(); save(form) }}>
      <label>Commission item<input required value={form.label} onChange={e => update(form.id, { label: e.target.value })}/></label>
      {form.calculation_type === 'overtime' ? <label>Overtime multiplier<input required type="number" min="0" step="0.01" value={form.overtime_multiplier ?? form.rate} onChange={e => update(form.id, { overtime_multiplier: e.target.value })}/></label> : <label>Rate (R)<input required type="number" min="0" step="0.01" value={form.rate} onChange={e => update(form.id, { rate: e.target.value })}/></label>}
      <label className="mortuary-confirm"><input type="checkbox" checked={form.is_active} onChange={e => update(form.id, { is_active: e.target.checked })}/>Active</label>
      <button className="primary-button" disabled={busy !== null}>{busy === form.id ? 'Saving…' : 'Save rate'}</button>
    </form>)}</div>
  </section>
}

export default function CommissionSettingsPage() {
  return <section className="mortuary-book">
    <header className="form-card"><h1>Commission Rates</h1><p>Configure removal fees, receipt percentages, VAT and other commissions here. Working hours are maintained in Add/Edit Staff.</p><p className="muted">A matching Mortuary Book, MF Invoice and payment receipts covering the full invoice are compulsory before any commission can be approved for payment. Set staff eligibility and branch-specific employee percentages under HR Staff → All Branches &amp; Commissions.</p></header>
    <RemovalSettings />
    <ReceiptSettings />
    <OtherCommissionSettings />
  </section>
}
