import { useEffect, useMemo, useState } from 'react'
import { applyLeave, approveLeaveApplication, declineLeaveApplication, getLeaveApplications, getLeaveBalance } from '../api/client'

const leaveTypes = ['Annual Leave', 'Sick Leave', 'Family Responsibility Leave', 'Unpaid Leave', 'Study Leave']

function parseDdMmYyyy(value) {
  if (!value) return null
  const m = String(value).trim().match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/)
  if (!m) return null
  const day = Number(m[1])
  const month = Number(m[2])
  const year = Number(m[3])
  const d = new Date(year, month - 1, day)
  if (d.getFullYear() !== year || d.getMonth() !== month - 1 || d.getDate() !== day) return null
  return d
}

function isoFromDdMmYyyy(value) {
  const d = parseDdMmYyyy(value)
  if (!d) return ''
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function toDateOnly(value) {
  if (!value) return null
  if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(String(value))) return parseDdMmYyyy(value)
  const d = new Date(`${value}T00:00:00`)
  return Number.isNaN(d.getTime()) ? null : d
}

function formatDate(value) {
  const d = toDateOnly(value)
  if (!d) return '—'
  return d.toLocaleDateString('en-ZA', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

function addDays(date, days) {
  const d = new Date(date)
  d.setDate(d.getDate() + days)
  return d
}

function sameDate(a, b) {
  return a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

function formatLeaveRange(start, end) {
  if (!start || !end) return 'Dates pending'
  const month = start.toLocaleString('en-ZA', { month: 'short' })
  if (sameDate(start, end)) return `${start.getDate()} ${month}`
  return `${start.getDate()}–${end.getDate()} ${month}`
}

function LeaveReturnTimeline({ items = [] }) {
  const approved = items
    .map((item) => {
      const start = toDateOnly(item.start_date || item.leave_start)
      const end = toDateOnly(item.end_date || item.leave_end)
      const returnDate = item.return_date ? toDateOnly(item.return_date) : (end ? addDays(end, 1) : null)
      const fullName = [item.name || item.full_name, item.surname].filter(Boolean).join(' ').trim() || item.email || 'Employee'
      return { ...item, full_name: fullName, start, end, returnDate }
    })
    .filter((item) => item.start && item.end && String(item.status || item.status_code || '').toLowerCase() === 'approved')
    .sort((a, b) => a.start - b.start || String(a.full_name || '').localeCompare(String(b.full_name || '')))

  const monthKeys = []
  approved.forEach((item) => {
    const cursor = new Date(item.start.getFullYear(), item.start.getMonth(), 1)
    const last = new Date((item.returnDate || item.end).getFullYear(), (item.returnDate || item.end).getMonth(), 1)
    while (cursor <= last) {
      const key = `${cursor.getFullYear()}-${cursor.getMonth()}`
      if (!monthKeys.includes(key)) monthKeys.push(key)
      cursor.setMonth(cursor.getMonth() + 1)
    }
  })
  monthKeys.sort((a, b) => {
    const [ay, am] = a.split('-').map(Number)
    const [by, bm] = b.split('-').map(Number)
    return new Date(ay, am, 1) - new Date(by, bm, 1)
  })

  return (
    <section className="form-card staff-list-card leave-return-card">
      <div className="detail-header leave-return-header">
        <div>
          <p className="eyebrow">Leave return planner</p>
          <h2>Approved leave and return dates</h2>
          <p className="muted">Shows every approved employee and manager leave record in your franchise scope. Red blocks are leave days. Green marks the date the user comes back.</p>
        </div>
        <div className="leave-return-legend">
          <span><i className="leave-day-swatch" /> On leave</span>
          <span><i className="return-day-swatch" /> Back at work</span>
        </div>
      </div>

      {monthKeys.map((key) => {
        const [year, month] = key.split('-').map(Number)
        const monthStart = new Date(year, month, 1)
        const monthEnd = new Date(year, month + 1, 0)
        const days = Array.from({ length: monthEnd.getDate() }, (_, idx) => new Date(year, month, idx + 1))
        const monthLabel = monthStart.toLocaleString('en-ZA', { month: 'long', year: 'numeric' })
        const monthItems = approved.filter((item) => item.start <= monthEnd && (item.returnDate || item.end) >= monthStart)
        return (
          <div className="leave-timeline-shell" key={`leave-month-${key}`}>
            <h3 className="leave-month-title">{monthLabel}</h3>
            <div className="leave-timeline-days" aria-hidden="true">
              <span />
              {days.map((day) => <small key={`leave-page-day-${key}-${day.getDate()}`}>{day.getDate()}</small>)}
            </div>
            {monthItems.map((item) => (
              <div className="leave-timeline-row" key={`leave-page-return-${key}-${item.id || item.application_id || item.user_id}-${item.start_date || item.leave_start}`}>
                <div className="leave-timeline-name">
                  <strong>{item.full_name}</strong>
                  <small>{formatLeaveRange(item.start, item.end)} · back {item.returnDate ? item.returnDate.toLocaleDateString('en-ZA', { day: 'numeric', month: 'short' }) : 'after leave'}</small>
                </div>
                <div className="leave-timeline-blocks" role="img" aria-label={`${item.full_name} leave from ${formatLeaveRange(item.start, item.end)}`}>
                  {days.map((day) => {
                    const onLeave = item.start <= day && day <= item.end
                    const returns = sameDate(day, item.returnDate)
                    return <span key={`${key}-${item.id || item.application_id || item.user_id}-${day.getDate()}`} className={`leave-day-cell ${onLeave ? 'on-leave' : ''} ${returns ? 'returns' : ''}`} />
                  })}
                </div>
              </div>
            ))}
          </div>
        )
      })}
    </section>
  )
}

export default function LeavePage({ me }) {
  const canDecide = me.roles.includes('SuperUser') || me.roles.includes('FranchiseUser') || me.roles.includes('ManagerUser')
  const canApply = me.roles.includes('EmployeeUser') || me.roles.includes('ManagerUser')
  const [balance, setBalance] = useState(null)
  const [apps, setApps] = useState([])
  const [form, setForm] = useState({ leave_type: 'Annual Leave', start_date_display: '', end_date_display: '', reason: '' })
  const [status, setStatus] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = async () => {
    setErr('')
    try {
      if (canApply) setBalance(await getLeaveBalance())
      setApps(await getLeaveApplications(status))
    } catch (e) {
      setErr(e.message || 'Failed to load leave information')
    }
  }

  useEffect(() => { load() }, [status])

  const daysRequested = useMemo(() => {
    const start = parseDdMmYyyy(form.start_date_display)
    const end = parseDdMmYyyy(form.end_date_display)
    if (!start || !end || end < start) return 0
    return Math.round((end - start) / 86400000) + 1
  }, [form.start_date_display, form.end_date_display])

  const submit = async (e) => {
    e.preventDefault()
    setMsg('')
    setErr('')
    const startIso = isoFromDdMmYyyy(form.start_date_display)
    const endIso = isoFromDdMmYyyy(form.end_date_display)
    if (!startIso || !endIso) {
      setErr('Please enter dates as dd/mm/yyyy, for example 07/05/2026.')
      return
    }
    if (!daysRequested) {
      setErr('End date cannot be before start date.')
      return
    }
    try {
      await applyLeave({ leave_type: form.leave_type, start_date: startIso, end_date: endIso, reason: form.reason })
      setMsg('Leave application submitted for approval.')
      setForm({ leave_type: 'Annual Leave', start_date_display: '', end_date_display: '', reason: '' })
      await load()
    } catch (error) {
      setErr(error.message || 'Could not submit leave application')
    }
  }

  const decide = async (id, action) => {
    const note = window.prompt(action === 'approve' ? 'Approval note optional' : 'Decline reason optional') || ''
    setErr('')
    setMsg('')
    try {
      if (action === 'approve') await approveLeaveApplication(id, note)
      else await declineLeaveApplication(id, note)
      setMsg(`Leave application ${action === 'approve' ? 'approved' : 'declined'}.`)
      await load()
    } catch (e) {
      setErr(e.message || 'Could not update leave application')
    }
  }

  return (
    <div className="leave-page">
      <section className="section-header compact-header">
        <p className="eyebrow">Leave Management</p>
        <h2>Leave Applications</h2>
        <p className="muted">Apply for leave and review pending applications in your allowed franchise or manager scope.</p>
      </section>
      {msg ? <p className="success">{msg}</p> : null}
      {err ? <p className="error">{err}</p> : null}

      {canApply ? (
        <section className="leave-grid">
          <div className="form-card">
            <h2>Leave days accumulated</h2>
            <div className="stat-grid mini">
              <div className="stat-card"><strong>{Number(balance?.annual_days_allocated || 0)}</strong><span>Allocated days</span></div>
              <div className="stat-card"><strong>{Number(balance?.annual_days_taken || 0)}</strong><span>Days taken</span></div>
              <div className="stat-card"><strong>{Number(balance?.days_remaining || 0)}</strong><span>Days available</span></div>
            </div>
          </div>
          <form className="form-card staff-form-single" onSubmit={submit}>
            <h2>Apply for leave</h2>
            <label>Leave type<select value={form.leave_type} onChange={(e) => setForm({ ...form, leave_type: e.target.value })}>{leaveTypes.map((t) => <option key={t}>{t}</option>)}</select></label>
            <label>Start date<input inputMode="numeric" placeholder="dd/mm/yyyy" value={form.start_date_display} onChange={(e) => setForm({ ...form, start_date_display: e.target.value })} required /></label>
            <label>End date<input inputMode="numeric" placeholder="dd/mm/yyyy" value={form.end_date_display} onChange={(e) => setForm({ ...form, end_date_display: e.target.value })} required /></label>
            <label>Days requested<input value={daysRequested || ''} readOnly /></label>
            <label className="wide">Reason<textarea value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="Optional reason" /></label>
            <button className="primary-action">Submit leave application</button>
          </form>
        </section>
      ) : null}

      <LeaveReturnTimeline items={apps} year={2026} month={4} />

      <section className="form-card staff-list-card">
        <div className="list-header"><h2>{canDecide ? 'Leave applications to review' : 'My leave applications'}</h2><label>Status<select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="declined">Declined</option></select></label></div>
        <div className="table-wrap"><table><thead><tr><th>Employee</th><th>Type</th><th>Dates</th><th>Days</th><th>Status</th><th>Reason</th><th>Decision</th></tr></thead><tbody>{apps.map((a) => <tr key={a.id}><td><strong>{a.name || a.full_name} {a.surname || ''}</strong><small>{a.role || a.email}</small></td><td>{a.leave_type}</td><td>{formatDate(a.start_date)} to {formatDate(a.end_date)}</td><td>{Number(a.days_requested || 0)}</td><td><span className={`status-pill ${a.status}`}>{a.status}</span></td><td>{a.reason || '—'}</td><td>{canDecide && a.status === 'pending' ? <div className="action-row"><button type="button" className="link-button" onClick={() => decide(a.id, 'approve')}>Accept</button><button type="button" className="link-button danger" onClick={() => decide(a.id, 'decline')}>Decline</button></div> : (a.decision_note || '—')}</td></tr>)}{!apps.length ? <tr><td colSpan="7" className="muted">No leave applications found.</td></tr> : null}</tbody></table></div>
      </section>
    </div>
  )
}
