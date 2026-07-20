import { useEffect, useState } from 'react'
import Card from '../components/Card'
import {
  approveAttendanceEvent,
  getAttendanceApprovals,
  getAttendanceFranchises,
  getAttendanceVisibleUsers,
  rejectAttendanceEvent,
} from '../api/client'

function formatTime(value) {
  if (!value) return 'n/a'
  return new Date(value).toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function statusClass(value) {
  if (value === 'approved') return 'badge good'
  if (value === 'rejected') return 'badge bad'
  return 'badge warn'
}

function userDisplay(row) {
  const name = row.user_full_name || [row.user_name, row.user_surname].filter(Boolean).join(' ')
  const detail = row.user_role || row.user_staff_type || row.user_email
  return { name: name || `User #${row.user_id}`, detail }
}

function UserCell({ row }) {
  const user = userDisplay(row)
  return <div className="user-display-cell"><strong>{user.name}</strong><span>{user.detail || `User ID ${row.user_id}`}</span></div>
}

export default function AttendanceApprovalPage({ me }) {
  const isSuperUser = me?.roles?.includes('SuperUser')
  const [approvalStatus, setApprovalStatus] = useState('pending')
  const [franchiseId, setFranchiseId] = useState('')
  const [franchises, setFranchises] = useState([])
  const [users, setUsers] = useState([])
  const [userId, setUserId] = useState('')
  const [items, setItems] = useState([])
  const [notes, setNotes] = useState({})
  const [reasons, setReasons] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const loadFranchises = async () => {
    if (!isSuperUser) return
    try {
      const data = await getAttendanceFranchises()
      const approved = (data.items || []).filter((f) => f.franchise_id)
      setFranchises(approved)
      if (!franchiseId && approved.length) setFranchiseId(String(approved[0].franchise_id))
    } catch (err) {
      setError(err.message || 'Failed to load franchises')
    }
  }

  const loadUsers = async () => {
    try {
      const data = await getAttendanceVisibleUsers(isSuperUser ? franchiseId : '')
      setUsers(data.items || [])
      setUserId('')
    } catch (err) {
      setUsers([])
      setError(err.message || 'Failed to load users')
    }
  }

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await getAttendanceApprovals({ approvalStatus, userId, franchiseId: isSuperUser ? franchiseId : '' })
      setItems(data.items || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadFranchises() }, [])
  useEffect(() => { loadUsers() }, [franchiseId])
  useEffect(() => { load() }, [approvalStatus, userId, franchiseId])

  const approve = async (id) => {
    setError('')
    setMessage('')
    try {
      await approveAttendanceEvent(id, { manager_note: notes[id] || null })
      setMessage(`Approved event #${id}`)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  const reject = async (id) => {
    setError('')
    setMessage('')
    try {
      if (!reasons[id]) throw new Error('Rejected reason is required')
      await rejectAttendanceEvent(id, { manager_note: notes[id] || null, rejected_reason: reasons[id] })
      setMessage(`Rejected event #${id}`)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <Card title="Attendance Approval">
      <p className="muted">Use the filters to view pending, approved, rejected or all attendance events in your allowed franchise scope.</p>
      <div className="history-toolbar approval-toolbar">
        {isSuperUser ? (
          <label>
            Franchise
            <select value={franchiseId} onChange={(event) => setFranchiseId(event.target.value)}>
              {franchises.map((f) => <option key={f.franchise_id} value={f.franchise_id}>{f.label} ({f.status})</option>)}
              {!franchises.length ? <option value="">No franchises found</option> : null}
            </select>
          </label>
        ) : null}
        <label>
          Status
          <select value={approvalStatus} onChange={(event) => setApprovalStatus(event.target.value)}>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="all">All</option>
          </select>
        </label>
        <label>
          User
          <select value={userId} onChange={(event) => setUserId(event.target.value)}>
            <option value="">All users in selected scope</option>
            {users.map((u) => <option key={u.user_id} value={u.user_id}>{u.label}{u.detail ? ` - ${u.detail}` : ''}</option>)}
          </select>
        </label>
        <button onClick={load} disabled={loading}>{loading ? 'Loading...' : 'Refresh'}</button>
      </div>

      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <div className="table-wrap">
        <table className="history-table approval-table">
          <thead>
            <tr>
              <th>Event</th>
              <th>User</th>
              <th>GPS / Area</th>
              <th>Signature</th>
              <th>Notes</th>
              <th>Decision</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => {
              const finalised = row.approval_status === 'approved' || row.approval_status === 'rejected'
              return (
                <tr key={row.id} className={`status-row status-${row.approval_status}`}>
                  <td>
                    <strong>#{row.id} {row.action}</strong>
                    <div className="muted small">{formatTime(row.created_at)}</div>
                    <div><span className={statusClass(row.approval_status)}>{row.approval_status || 'pending'}</span></div>
                    <div className="muted small">Work: {row.work_location_type || 'n/a'}</div>
                  </td>
                  <td><UserCell row={row} /></td>
                  <td>
                    <div><strong>{row.gps_status || 'n/a'}</strong></div>
                    <div className="muted small">Distance: {row.distance_from_site_m == null ? 'n/a' : `${Math.round(row.distance_from_site_m)} m`}</div>
                    <div className="muted small">Accuracy: {row.accuracy_meters || 'n/a'}</div>
                    <div className="muted small">{row.latitude}, {row.longitude}</div>
                    {row.map_url ? <a href={row.map_url} target="_blank" rel="noreferrer">Open map</a> : null}
                  </td>
                  <td>
                    <div>{row.signature_status || 'n/a'}</div>
                    <div className="muted small">Signature data saved in event record</div>
                  </td>
                  <td>
                    <div><strong>Employee:</strong> {row.employee_note || 'n/a'}</div>
                    {!finalised ? (
                      <>
                        <label className="small-label">Manager note
                          <textarea value={notes[row.id] || ''} onChange={(event) => setNotes({ ...notes, [row.id]: event.target.value })} />
                        </label>
                        <label className="small-label">Reject reason
                          <textarea value={reasons[row.id] || ''} onChange={(event) => setReasons({ ...reasons, [row.id]: event.target.value })} />
                        </label>
                      </>
                    ) : null}
                    {row.manager_note ? <div className="muted small"><strong>Manager note:</strong> {row.manager_note}</div> : null}
                  </td>
                  <td>
                    {!finalised ? (
                      <div className="button-stack">
                        <button onClick={() => approve(row.id)}>Approve</button>
                        <button className="danger" onClick={() => reject(row.id)}>Reject</button>
                      </div>
                    ) : <span className={statusClass(row.approval_status)}>{row.approval_status === 'approved' ? 'Approved' : 'Rejected'}</span>}
                    {row.approved_by_user_id ? <div className="muted small">By: {row.approved_by_user_id}</div> : null}
                    {row.approved_at ? <div className="muted small">At: {formatTime(row.approved_at)}</div> : null}
                    {row.rejected_reason ? <div className="error small">Rejected: {row.rejected_reason}</div> : null}
                  </td>
                </tr>
              )
            })}
            {!items.length ? <tr><td colSpan="6" className="muted">No approval records found.</td></tr> : null}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
