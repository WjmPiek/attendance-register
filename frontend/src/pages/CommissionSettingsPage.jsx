import { useEffect, useState } from 'react'
import RemovalSettings from '../components/RemovalSettings'
import ReceiptSettings from '../components/ReceiptSettings'
import { getCommissionStructures, saveCommissionStructure } from '../api/client'

function OtherCommissionSettings() {
  const [structures, setStructures] = useState([]), [form, setForm] = useState(null)
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false)
  const load = async () => {
    const rows = (await getCommissionStructures()).filter(s => !['removals', 'invoice_commission'].includes(s.commission_type))
    setStructures(rows)
    setForm(current => rows.find(s => s.commission_type === current?.commission_type) || rows[0] || null)
  }
  useEffect(() => { load().catch(e => setError(e.message)) }, [])
  const save = async event => {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      await saveCommissionStructure({ ...form, rate: Number(form.rate), overtime_multiplier: form.calculation_type === 'overtime' ? Number(form.overtime_multiplier || 1) : null })
      await load(); setNotice('Commission rate saved.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <section className="form-card">
    <h2>Other commissions and overtime</h2>
    {error && <p role="alert" className="error-message">{error}</p>}{notice && <p role="status" className="success-message">{notice}</p>}
    {form && <form className="form-grid" onSubmit={save}>
      <label>Commission<select value={form.commission_type} onChange={e => { setForm(structures.find(s => s.commission_type === e.target.value)); setNotice('') }}>{structures.map(s => <option key={s.id} value={s.commission_type}>{s.label}</option>)}</select></label>
      <label>Display label<input required value={form.label} onChange={e => setForm(v => ({ ...v, label: e.target.value }))}/></label>
      {form.calculation_type === 'overtime' ? <label>Overtime multiplier<input required type="number" min="0" step="0.01" value={form.overtime_multiplier ?? form.rate} onChange={e => setForm(v => ({ ...v, overtime_multiplier: e.target.value }))}/></label> : <label>Rate (R)<input required type="number" min="0" step="0.01" value={form.rate} onChange={e => setForm(v => ({ ...v, rate: e.target.value }))}/></label>}
      <label className="mortuary-confirm"><input type="checkbox" checked={form.is_active} onChange={e => setForm(v => ({ ...v, is_active: e.target.checked }))}/>Category active</label>
      <button className="primary-button" disabled={busy}>{busy ? 'Saving…' : 'Save commission rate'}</button>
    </form>}
  </section>
}

export default function CommissionSettingsPage() {
  return <section className="mortuary-book">
    <header className="form-card"><h1>Configure Hours and Rates</h1><p>Configure franchise hours, removal fees, receipt percentages, VAT and other commissions here.</p><p className="muted">A matching Mortuary Book, MF Invoice and payment receipts covering the full invoice are compulsory before any commission can be approved for payment. Set staff eligibility and branch-specific employee percentages under HR Staff → All Branches &amp; Commissions.</p></header>
    <RemovalSettings />
    <ReceiptSettings />
    <OtherCommissionSettings />
  </section>
}
