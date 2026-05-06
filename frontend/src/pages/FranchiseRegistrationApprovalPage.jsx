import { useEffect, useState } from 'react'
import { approveFranchiseRegistration, getFranchiseRegistrations, rejectFranchiseRegistration, updateFranchiseRegistration } from '../api/client'
import Card from '../components/Card'

export default function FranchiseRegistrationApprovalPage({ me }) {
  const [statusFilter, setStatusFilter] = useState('pending')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [notes, setNotes] = useState({})
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({})

  const isSuperUser = me.roles.includes('SuperUser')

  const load = async () => {
    if (!isSuperUser) return
    setLoading(true)
    setError('')
    try {
      const list = await getFranchiseRegistrations(statusFilter)
      setItems(Array.isArray(list) ? list : [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [statusFilter])

  const setNote = (id, value) => setNotes((current) => ({ ...current, [id]: value }))

  const approve = async (id) => {
    setMessage('')
    setError('')
    try {
      await approveFranchiseRegistration(id, notes[id] || '')
      setMessage('Franchise registration approved and user account created')
      await load()
    } catch (err) {
      setError(err.message)
    }
  }



  const beginEdit = (item) => {
    setError('')
    setMessage('')
    setEditingId(item.id)
    setEditForm({
      business_name: item.business_name || '',
      trading_as: item.trading_as || '',
      business_registration_number: item.business_registration_number || '',
      vat_number: item.vat_number || '',
      office_address: item.office_address || '',
      website: item.website || '',
      office_number: item.office_number || '',
      twenty_four_hour_number: item.twenty_four_hour_number || '',
      franchisee_name: item.franchisee_name || '',
      franchisee_surname: item.franchisee_surname || '',
      email: item.email || '',
      contact_number: item.contact_number || '',
    })
  }

  const saveEdit = async (id) => {
    setMessage('')
    setError('')
    try {
      await updateFranchiseRegistration(id, editForm)
      setEditingId(null)
      setEditForm({})
      setError('')
      setMessage('Franchise details updated')
      await load()
    } catch (err) {
      setError(err.message || 'Failed to update franchise')
    }
  }

  const updateEdit = (key, value) => setEditForm((current) => ({ ...current, [key]: value }))

  const reject = async (id) => {
    const note = notes[id] || ''
    if (!note.trim()) {
      setError('Enter a rejection reason before rejecting')
      return
    }
    setMessage('')
    setError('')
    try {
      await rejectFranchiseRegistration(id, note)
      setMessage('Franchise registration rejected')
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  if (!isSuperUser) return null

  return (
    <Card title="Franchise Registration Approvals">
      <div className="history-toolbar">
        <label>Status
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="all">All</option>
          </select>
        </label>
        <button type="button" onClick={load} disabled={loading}>{loading ? 'Loading...' : 'Refresh'}</button>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}

      <div className="approval-list franchise-approval-list">
        {items.length === 0 ? <p className="muted">No franchise registrations found.</p> : null}
        {items.map((item) => (
          <div className="approval-item franchise-approval-card" key={item.id}>
            <div className="approval-header">
              <div>
                <h3>{item.business_name}</h3>
                <p className="muted">Trading as: {item.trading_as || 'Not supplied'}</p>
              </div>
              <div className="action-links"><button type="button" className="link-button" onClick={() => beginEdit(item)}>Edit</button><span className={`badge ${item.status === 'approved' ? 'good' : item.status === 'rejected' ? 'bad' : 'warn'}`}>{item.status}</span></div>
            </div>

            <div className="details-grid franchise-details-grid">
              <div><strong>Business Reg:</strong> {item.business_registration_number || '-'}</div>
              <div><strong>VAT Nr:</strong> {item.vat_number || '-'}</div>
              <div><strong>Office Number:</strong> {item.office_number || '-'}</div>
              <div><strong>24 Hour Number:</strong> {item.twenty_four_hour_number || '-'}</div>
              <div className="span-2"><strong>Office Address:</strong> {item.office_address || '-'}</div>
              <div className="span-2"><strong>Website:</strong> {item.website || '-'}</div>
              <div><strong>Franchisee:</strong> {item.franchisee_name} {item.franchisee_surname}</div>
              <div><strong>Email:</strong> {item.email}</div>
              <div><strong>Contact:</strong> {item.contact_number || '-'}</div>
              <div><strong>Submitted:</strong> {new Date(item.created_at).toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</div>
              {item.rejected_reason ? <div className="span-2"><strong>Rejected reason:</strong> {item.rejected_reason}</div> : null}
            </div>

            {editingId === item.id ? (
              <div className="decision-box franchise-edit-box">
                <h4>Edit Franchise Details</h4>
                <div className="form-grid">
                  <label>Business Name<input value={editForm.business_name || ''} onChange={(e) => updateEdit('business_name', e.target.value)} /></label>
                  <label>Trading As<input value={editForm.trading_as || ''} onChange={(e) => updateEdit('trading_as', e.target.value)} /></label>
                  <label>Business Registration<input value={editForm.business_registration_number || ''} onChange={(e) => updateEdit('business_registration_number', e.target.value)} /></label>
                  <label>VAT Nr<input value={editForm.vat_number || ''} onChange={(e) => updateEdit('vat_number', e.target.value)} /></label>
                  <label className="span-2">Office Address<input value={editForm.office_address || ''} onChange={(e) => updateEdit('office_address', e.target.value)} /></label>
                  <label className="span-2">Website Address<input value={editForm.website || ''} onChange={(e) => updateEdit('website', e.target.value)} placeholder="https://example.co.za" /></label>
                  <label>Office Number<input value={editForm.office_number || ''} onChange={(e) => updateEdit('office_number', e.target.value)} /></label>
                  <label>24 Hour Number<input value={editForm.twenty_four_hour_number || ''} onChange={(e) => updateEdit('twenty_four_hour_number', e.target.value)} /></label>
                  <label>Franchisee Name<input value={editForm.franchisee_name || ''} onChange={(e) => updateEdit('franchisee_name', e.target.value)} /></label>
                  <label>Franchisee Surname<input value={editForm.franchisee_surname || ''} onChange={(e) => updateEdit('franchisee_surname', e.target.value)} /></label>
                  <label>Email<input value={editForm.email || ''} onChange={(e) => updateEdit('email', e.target.value)} /></label>
                  <label>Contact<input value={editForm.contact_number || ''} onChange={(e) => updateEdit('contact_number', e.target.value)} /></label>
                </div>
                <div className="button-row">
                  <button type="button" onClick={() => saveEdit(item.id)}>Save Franchise Details</button>
                  <button type="button" className="secondary" onClick={() => setEditingId(null)}>Cancel</button>
                </div>
              </div>
            ) : null}

            {item.status === 'pending' ? (
              <div className="decision-box">
                <label>Manager/Admin Note or Rejection Reason
                  <textarea value={notes[item.id] || ''} onChange={(event) => setNote(item.id, event.target.value)} placeholder="Optional note for approval, required for rejection" />
                </label>
                <div className="button-row">
                  <button type="button" onClick={() => approve(item.id)}>Approve and Create Franchise User</button>
                  <button type="button" className="danger" onClick={() => reject(item.id)}>Reject</button>
                </div>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </Card>
  )
}
