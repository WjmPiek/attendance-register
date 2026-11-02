import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'

export default function ImportBranchScope({ franchiseId, value, onChange }) {
  const [data, setData] = useState({ branches: [], can_manage: false }), [name, setName] = useState(''), [vat, setVat] = useState(''), [error, setError] = useState('')
  const suffix = franchiseId ? `?franchise_user_id=${encodeURIComponent(franchiseId)}` : ''
  const load = async () => setData(await apiRequest(`/receipt-commissions/external-branches${suffix}`))
  useEffect(() => { load().catch(e => setError(e.message)) }, [suffix])
  const add = async () => {
    setError('')
    try {
      const row = await apiRequest('/receipt-commissions/external-branches', { method: 'POST', body: JSON.stringify({ name, vat_number: vat || null, franchise_user_id: franchiseId ? Number(franchiseId) : null }) })
      await load(); onChange(String(row.id)); setName(''); setVat('')
    } catch (e) { setError(e.message) }
  }
  return <section className="form-card"><label>Documents for<select value={value || ''} onChange={e => onChange(e.target.value)}><option value="">One of the holder’s linked branches</option>{data.branches.map(branch => <option value={branch.id} key={branch.id}>Outside branch: {branch.name}</option>)}</select></label><p className="muted">Choose the printed outside branch for external service documents. The same branch must appear on the Mortuary Book, Invoice and Receipts.</p>{data.can_manage && <details><summary>Declare an outside service branch</summary><div className="form-grid"><label>Printed branch name<input value={name} onChange={e => setName(e.target.value)}/></label><label>Branch VAT number, if registered<input value={vat} onChange={e => setVat(e.target.value)} placeholder="10 digits, optional"/></label><button type="button" className="glass-button" disabled={name.trim().length < 2} onClick={add}>Add outside branch</button></div></details>}{error && <p role="alert" className="error-message">{error}</p>}</section>
}
