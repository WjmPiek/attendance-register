import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'
import ImportFeedback from './ImportFeedback'

export default function ImportBranchScope({ franchiseId, value, onChange }) {
  const [data, setData] = useState({ branches: [], can_manage: false }), [name, setName] = useState(''), [vat, setVat] = useState(''), [error, setError] = useState('')
  const [linked,setLinked]=useState([])
  const suffix = franchiseId ? `?franchise_user_id=${encodeURIComponent(franchiseId)}` : ''
  const load = async () => {const [outside,inside]=await Promise.all([apiRequest(`/receipt-commissions/external-branches${suffix}`),apiRequest(`/receipt-commissions/branches${suffix}`)]);setData(outside);setLinked(inside)}
  useEffect(() => { load().catch(e => setError(e.message)) }, [suffix])
  const add = async () => {
    setError('')
    try {
      const row = await apiRequest('/receipt-commissions/external-branches', { method: 'POST', body: JSON.stringify({ name, vat_number: vat || null, franchise_user_id: franchiseId ? Number(franchiseId) : null }) })
      await load(); onChange(`external:${row.id}`); setName(''); setVat('')
    } catch (e) { setError(e.message) }
  }
  return <section className="form-card"><ImportFeedback error={error}/><label>Documents for<select value={value || ''} onChange={e => onChange(e.target.value)}><option value="">Automatically detect linked branch from the document</option>{linked.map(branch=><option value={`linked:${branch.id}`} key={`linked:${branch.id}`}>{branch.name}</option>)}{data.branches.map(branch => <option value={`external:${branch.id}`} key={`external:${branch.id}`}>Outside branch: {branch.name}</option>)}</select></label><p className="muted">All linked branches are listed automatically. Leave automatic detection selected for a batch containing different linked branches. The printed branch, MF number and invoice/receipt details fill from each PDF; selecting a branch checks that the document belongs there.</p>{data.can_manage && <details><summary>Declare an outside service branch</summary><div className="form-grid"><label>Printed branch name<input value={name} onChange={e => setName(e.target.value)}/></label><label>Branch VAT number, if registered<input value={vat} onChange={e => setVat(e.target.value)} placeholder="10 digits, optional"/></label><button type="button" className="glass-button" disabled={name.trim().length < 2} onClick={add}>Add outside branch</button></div></details>}{error && <p role="alert" className="error-message">{error}</p>}</section>
}
