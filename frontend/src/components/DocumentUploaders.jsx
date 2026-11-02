import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'

export default function DocumentUploaders({ franchiseId }) {
  const [staff, setStaff] = useState([]), [selected, setSelected] = useState([]), [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false)
  const suffix = franchiseId ? `?franchise_user_id=${encodeURIComponent(franchiseId)}` : ''
  useEffect(() => { apiRequest(`/receipt-commissions/uploaders${suffix}`).then(rows => { setStaff(rows); setSelected(rows.filter(row => row.can_import_commissions).map(row => row.user_id)) }).catch(e => setError(e.message)) }, [suffix])
  const save = async () => {
    setBusy(true); setError(''); setNotice('')
    try {
      await apiRequest('/receipt-commissions/uploaders', { method: 'PUT', body: JSON.stringify({ franchise_user_id: franchiseId ? Number(franchiseId) : null, employee_user_ids: selected }) })
      setNotice('Document uploaders saved. Selected staff receive an Upload proof option and notices when claims need documents.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <section className="form-card"><h3>Document uploaders</h3><p>Select one or more managers and employees who should upload closed-file documents promptly. This grants document import access; it does not grant claim approval or HR access.</p><div className="commission-checkbox-grid">{staff.map(person => <label key={person.user_id}><input type="checkbox" checked={selected.includes(person.user_id)} disabled={busy} onChange={e => setSelected(values => e.target.checked ? [...values, person.user_id] : values.filter(id => id !== person.user_id))}/>{person.full_name} · {person.employee_role} · {person.branch_name}</label>)}</div><button type="button" className="primary-button" disabled={busy} onClick={save}>Save document uploaders</button>{error && <p role="alert" className="error-message">{error}</p>}{notice && <p role="status" className="success-message">{notice}</p>}</section>
}
