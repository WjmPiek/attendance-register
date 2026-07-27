import { useEffect, useMemo, useState } from 'react'
import {
  approveAttendanceEvent,
  approveLeaveApplication,
  declineLeaveApplication,
  getAttendanceApprovals,
  getAttendanceHistory,
  getCommissionEntries,
  getLeaveApplications,
  getNotifications,
  rejectAttendanceEvent,
} from '../api/client'

const formatDateTime = (value) => value
  ? new Date(value).toLocaleString('en-ZA', { dateStyle: 'medium', timeStyle: 'short' })
  : '—'

const statusClass = (value) => `status-pill ${String(value || 'pending').toLowerCase()}`
const listItems = (value) => Array.isArray(value) ? value : (Array.isArray(value?.items) ? value.items : [])
const gpsLabel = (value) => ({
  inside_area: 'Inside office GPS range',
  outside_area: 'Not in office GPS range',
  accuracy_too_low: 'GPS accuracy too low',
  on_road: 'On-road attendance',
}[value] || String(value || 'GPS pending').replaceAll('_', ' '))

export default function StaffWorkHub({ employee, onClose, onEdit, onNavigate }) {
  const [attendance, setAttendance] = useState([])
  const [attendancePending, setAttendancePending] = useState([])
  const [leave, setLeave] = useState([])
  const [commission, setCommission] = useState({ items: [], counts: {} })
  const [notifications, setNotifications] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const userId = Number(employee?.user_id || 0)
  const fullName = [employee?.name, employee?.surname].filter(Boolean).join(' ').trim() || employee?.full_name || 'Employee'

  const load = async () => {
    if (!userId) return
    setLoading(true)
    setError('')
    const results = await Promise.allSettled([
      getAttendanceHistory({ userId }),
      getAttendanceApprovals({ approvalStatus: 'pending', userId }),
      getLeaveApplications(''),
      getCommissionEntries({ employeeUserId: userId }),
      getNotifications(),
    ])
    const [historyResult, approvalResult, leaveResult, commissionResult, notificationResult] = results
    setAttendance(historyResult.status === 'fulfilled' ? listItems(historyResult.value) : [])
    setAttendancePending(approvalResult.status === 'fulfilled' ? listItems(approvalResult.value) : [])
    setLeave(leaveResult.status === 'fulfilled' && Array.isArray(leaveResult.value)
      ? leaveResult.value.filter((item) => Number(item.applicant_user_id) === userId)
      : [])
    setCommission(commissionResult.status === 'fulfilled' ? commissionResult.value : { items: [], counts: {} })
    setNotifications(notificationResult.status === 'fulfilled' && Array.isArray(notificationResult.value)
      ? notificationResult.value.filter((item) => Number(item.user_id) === userId)
      : [])
    const failed = results.find((result) => result.status === 'rejected')
    if (failed) setError(failed.reason?.message || 'Some employee activity could not load.')
    setLoading(false)
  }

  useEffect(() => { load() }, [userId])

  const pendingLeave = useMemo(
    () => leave.filter((item) => String(item.status || '').toLowerCase() === 'pending'),
    [leave]
  )

  const decideAttendance = async (event, approved) => {
    const note = window.prompt(approved ? 'Approval note (optional):' : 'Reason for rejection (required):', '')
    if (note === null || (!approved && !note.trim())) return
    setBusy(`attendance-${event.id}`)
    setError('')
    try {
      if (approved) await approveAttendanceEvent(event.id, { manager_note: note.trim() || null })
      else await rejectAttendanceEvent(event.id, { rejected_reason: note.trim() })
      setMessage(`Attendance ${approved ? 'approved' : 'rejected'} for ${fullName}.`)
      await load()
    } catch (err) { setError(err.message) }
    finally { setBusy('') }
  }

  const decideLeave = async (application, approved) => {
    const note = window.prompt(approved ? 'Approval note (optional):' : 'Reason for declining leave:', '')
    if (note === null) return
    setBusy(`leave-${application.id}`)
    setError('')
    try {
      if (approved) await approveLeaveApplication(application.id, note.trim())
      else await declineLeaveApplication(application.id, note.trim())
      setMessage(`Leave ${approved ? 'approved' : 'declined'} for ${fullName}.`)
      await load()
    } catch (err) { setError(err.message) }
    finally { setBusy('') }
  }

  const openCommissions = () => {
    const url = new URL(window.location.href)
    url.searchParams.set('commission_employee', String(userId))
    window.history.replaceState({}, '', url)
    onNavigate?.('commission')
  }

  if (!employee) return null

  return (
    <section className="form-card staff-work-hub">
      <div className="detail-header">
        <div>
          <p className="eyebrow">My Staff work hub</p>
          <h2>{fullName}</h2>
          <p className="muted">{employee.employee_role || 'Employee'} · {employee.employee_number || 'No employee number'} · {employee.office_name || employee.office_address_assigned || 'No office assigned'}</p>
        </div>
        <div className="button-row">
          {onEdit ? <button type="button" className="glass-button" onClick={onEdit}>Edit employee</button> : null}
          <button type="button" className="glass-button" onClick={openCommissions}>Open commissions</button>
          <button type="button" className="secondary-action" onClick={onClose}>Back to staff list</button>
        </div>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success-message">{message}</p> : null}
      {loading ? <p>Loading all employee activity...</p> : (
        <>
          <div className="stats-grid staff-work-summary">
            <div className="stat-card"><span>Attendance approvals</span><strong>{attendancePending.length}</strong></div>
            <div className="stat-card"><span>Leave approvals</span><strong>{pendingLeave.length}</strong></div>
            <div className="stat-card"><span>Pending commissions</span><strong>{commission?.counts?.pending || 0}</strong></div>
            <div className="stat-card"><span>Unread notifications</span><strong>{notifications.filter((item) => !item.is_read).length}</strong></div>
          </div>

          <section className="staff-work-section">
            <div className="section-heading"><div><h3>Attendance and sign in/out</h3><p className="muted small">Latest attendance evidence and every pending decision for this employee.</p></div></div>
            {attendancePending.length ? <div className="employee-approval-list">{attendancePending.map((item) => (
              <div className="employee-approval-row" key={`attendance-${item.id}`}>
                <div><strong>{String(item.action || '').replace('_', ' ')}</strong><span>{formatDateTime(item.created_at)} · {gpsLabel(item.gps_status)} · {item.distance_from_site_m == null ? 'No distance' : `${Math.round(item.distance_from_site_m)} m from office`}</span></div>
                <div className="button-row"><button type="button" disabled={busy === `attendance-${item.id}`} onClick={() => decideAttendance(item, true)}>Approve</button><button type="button" className="danger-button" disabled={busy === `attendance-${item.id}`} onClick={() => decideAttendance(item, false)}>Reject</button></div>
              </div>
            ))}</div> : <p className="muted">No pending attendance approvals.</p>}
            <div className="table-wrap"><table><thead><tr><th>Action</th><th>Date and time</th><th>GPS</th><th>Approval</th></tr></thead><tbody>
              {attendance.slice(0, 10).map((item) => <tr key={`event-${item.id}`}><td>{String(item.action || '').replace('_', ' ')}</td><td>{formatDateTime(item.created_at)}</td><td>{gpsLabel(item.gps_status)}{item.distance_from_site_m != null ? ` · ${Math.round(item.distance_from_site_m)} m from office` : ''}</td><td><span className={statusClass(item.approval_status)}>{item.approval_status || 'pending'}</span></td></tr>)}
              {!attendance.length ? <tr><td colSpan="4" className="muted">No attendance events yet.</td></tr> : null}
            </tbody></table></div>
          </section>

          <section className="staff-work-section">
            <h3>Leave</h3>
            {leave.length ? <div className="employee-approval-list">{leave.map((item) => (
              <div className="employee-approval-row" key={`leave-${item.id}`}>
                <div><strong>{item.leave_type}</strong><span>{item.start_date} to {item.end_date} · {item.days_requested} day(s) · {item.reason || 'No reason supplied'}</span><span className={statusClass(item.status)}>{item.status}</span></div>
                {String(item.status).toLowerCase() === 'pending' ? <div className="button-row"><button type="button" disabled={busy === `leave-${item.id}`} onClick={() => decideLeave(item, true)}>Approve</button><button type="button" className="danger-button" disabled={busy === `leave-${item.id}`} onClick={() => decideLeave(item, false)}>Decline</button></div> : null}
              </div>
            ))}</div> : <p className="muted">No active leave applications.</p>}
          </section>

          <section className="staff-work-section">
            <div className="section-heading"><div><h3>Commission and overtime</h3><p className="muted small">This employee’s claims remain separate from the manager’s own commission.</p></div><button type="button" onClick={openCommissions}>Review commissions</button></div>
            <div className="table-wrap"><table><thead><tr><th>Date</th><th>Reference</th><th>Type</th><th>Amount</th><th>Status</th></tr></thead><tbody>
              {(commission?.items || []).slice(0, 10).map((item) => <tr key={`commission-${item.id}`}><td>{item.service_date}</td><td>{item.reference}</td><td>{String(item.commission_type || '').replaceAll('_', ' ')}</td><td>R {Number(item.calculated_amount || 0).toFixed(2)}</td><td><span className={statusClass(item.status)}>{item.status}</span></td></tr>)}
              {!commission?.items?.length ? <tr><td colSpan="5" className="muted">No commission or overtime records.</td></tr> : null}
            </tbody></table></div>
          </section>

          <section className="staff-work-section">
            <h3>Employee notifications</h3>
            {notifications.slice(0, 10).map((item) => <div className="employee-notification-row" key={`notification-${item.id}`}><strong>{item.subject}</strong><span>{item.message}</span><small>{formatDateTime(item.created_at)} · {item.is_read ? 'Read' : 'Unread'}</small></div>)}
            {!notifications.length ? <p className="muted">No notifications for this employee.</p> : null}
          </section>
        </>
      )}
    </section>
  )
}
