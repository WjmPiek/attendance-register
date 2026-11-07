import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'
import './MortuaryBook.css'

export default function ReceiptSettings({ franchiseId }) {
  const [data, setData] = useState(null), [settings, setSettings] = useState(null)
  const [vatBranch, setVatBranch] = useState(0), [busy, setBusy] = useState(false)
  const [error, setError] = useState(''), [notice, setNotice] = useState('')
  const suffix = franchiseId ? `?franchise_user_id=${franchiseId}` : ''
  const load = async (branch = vatBranch) => {
    const d = await apiRequest(`/receipt-commissions/settings${suffix}${suffix ? '&' : '?'}branch_id=${branch}`)
    setData(d); setSettings(d.settings)
  }
  useEffect(() => { setVatBranch(0); load(0).catch(e => setError(e.message)) }, [suffix])
  const run = async action => { setBusy(true); setError(''); setNotice(''); try { await action() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const saveSettings = e => { e.preventDefault(); run(async () => {
    await apiRequest('/receipt-commissions/settings', { method: 'PUT', body: JSON.stringify({ ...settings, franchise_user_id: franchiseId ? Number(franchiseId) : null, vat_registered: settings.vat_registered === true || settings.vat_registered === 'true', receipt_percentage: settings.receipt_percentage === '' ? null : settings.receipt_percentage }) })
    await load(); setNotice('VAT record saved. Commission percentages are configured in the Commissions table.')
  }) }
  return <section className="mortuary-book">
    {error && <p role="alert" className="error-message">{error}</p>}
    {notice && <p role="status" className="success-message">{notice}</p>}
    {settings && <form className="form-card" onSubmit={saveSettings}><h3>Branch VAT records</h3><label>VAT settings for<select value={vatBranch} onChange={e => { const id = Number(e.target.value); setVatBranch(id); run(() => load(id)) }}><option value={0}>Holder defaults — inherited unless a branch differs</option>{data?.branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label><p>Confirm VAT status for the holder or selected branch. The main system determines VAT registration for linked branches. A blank main-system VAT number means no VAT is deducted, even when the invoice shows VAT.</p>{settings.vat_from_main_system&&<p role="status">VAT status comes from the main system. Change the branch VAT number there and reopen Attendance to sync it.</p>}<div className="mortuary-rates">
      <label>VAT registered<select disabled={settings.vat_from_main_system} required value={settings.vat_registered == null ? '' : String(settings.vat_registered)} onChange={e => setSettings(s => ({ ...s, vat_registered: e.target.value }))}><option value="">Confirm status</option><option value="true">Yes — calculate excluding VAT</option><option value="false">No — use the full invoice amount</option></select></label>
      <label>VAT registration number<input disabled={settings.vat_from_main_system} required={String(settings.vat_registered) === 'true'} value={settings.vat_number || ''} onChange={e => setSettings(s => ({ ...s, vat_number: e.target.value }))}/></label>
      <label>VAT rate (%)<input disabled={settings.vat_from_main_system&&!settings.vat_registered} type="number" min="0" max="100" step="0.0001" required value={settings.vat_rate} onChange={e => setSettings(s => ({ ...s, vat_rate: e.target.value }))}/></label>
</div><button className="primary-button" disabled={busy||(settings.vat_from_main_system&&!settings.vat_registered)}>Save VAT record</button></form>}
  </section>
}
