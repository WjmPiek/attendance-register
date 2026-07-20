import { useEffect, useState } from 'react'
import { getDashboardAlerts, markNotificationRead } from '../api/client'

function StatBlock({ title, value, subtitle, tone = '' }) {
  return (
    <div className={`metric-card ${tone}`}>
      <strong>{value}</strong>
      <span>{title}</span>
      {subtitle ? <small>{subtitle}</small> : null}
    </div>
  )
}

function OverviewMetricRail({ metrics = {}, lists = {} }) {
  const totalIssues = Number(metrics.not_signed_in || 0) + Number(metrics.late || 0) + Number(metrics.missing_sign_out || 0) + Number((lists.gps_issues || []).length || 0)
  const goodCount = Math.max(0, Number(metrics.completed || 0))
  return (
    <section className="overview-hero-panel">
      <div className="overview-hero-copy">
        <p className="eyebrow">Operations overview</p>
        <h2>Today’s control centre</h2>
        <p className="muted">Attendance, exceptions, leave and notifications for your current franchise scope.</p>
      </div>
      <div className="overview-metric-rail">
        <StatBlock title="Active staff" value={metrics.total_staff || 0} subtitle="In current scope" />
        <StatBlock title="Completed" value={goodCount} subtitle="Signed in and out" tone="success" />
        <StatBlock title="Open issues" value={totalIssues} subtitle="Needs review" tone={totalIssues ? 'danger' : 'success'} />
        <StatBlock title="Leave pending" value={metrics.pending_leave || 0} subtitle="Applications to review" tone={metrics.pending_leave ? 'warning' : ''} />
      </div>
    </section>
  )
}

function PersonList({ title, items = [], emptyText }) {
  return (
    <section className="form-card dashboard-list-card">
      <h2>{title}</h2>
      <div className="table-wrap compact-table">
        <table>
          <thead><tr><th>Name</th><th>Role</th><th>Manager</th><th>Office</th><th>Status</th></tr></thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${title}-${item.user_id}`}>
                <td><strong>{item.full_name}</strong><br /><span className="muted">{item.email || item.contact_number || 'No email/contact'}</span></td>
                <td>{item.role || item.staff_type || '—'}</td>
                <td>{item.manager_name || '—'}</td>
                <td>{item.office || '—'}</td>
                <td><span className={`status-pill ${item.status_code || ''}`}>{item.status_label || 'Review'}</span></td>
              </tr>
            ))}
            {!items.length ? <tr><td colSpan="5" className="muted">{emptyText}</td></tr> : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}


function InlineNotificationList({ title, count, items = [], emptyText, tone = '', renderDetail, actionLabel = 'Open', onOpen }) {
  return (
    <section className={`notification-card ${tone}`}>
      <div className="notification-card-head">
        <div>
          <strong>{title}</strong>
          <small>{count || 0} item(s)</small>
        </div>
        <span className={`notification-count ${tone}`}>{count || 0}</span>
      </div>
      <div className="notification-mini-list">
        {items.slice(0, 6).map((item) => (
          <button
            type="button"
            className="notification-mini-row notification-link-row"
            key={`${title}-${item.application_id || item.event_id || item.user_id}`}
            onClick={() => onOpen && onOpen(item)}
            title={actionLabel}
          >
            <div>
              <strong>{item.full_name}</strong>
              <small>{item.role || item.staff_type || item.email || 'Staff member'}</small>
            </div>
            <span>{renderDetail ? renderDetail(item) : (item.status_label || item.office || 'Review')}</span>
          </button>
        ))}
        {!items.length ? <p className="muted compact-empty">{emptyText}</p> : null}
        {items.length > 6 ? <small className="muted">+ {items.length - 6} more</small> : null}
      </div>
    </section>
  )
}

function OverviewNotifications({ lists = {}, metrics = {}, onNavigate }) {
  const go = (tabId) => {
    if (typeof onNavigate === 'function') onNavigate(tabId)
  }
  const approvedLeave = lists.approved_leave || []
  return (
    <section className="overview-notification-grid">
      <InlineNotificationList
        title="Not signed in today"
        count={metrics.not_signed_in || (lists.not_signed_in || []).length}
        items={lists.not_signed_in || []}
        emptyText="All active staff have signed in."
        tone="warning"
        renderDetail={(item) => item.manager_name ? `Manager: ${item.manager_name}` : 'No sign-in found'}
        actionLabel="Open attendance history"
        onOpen={() => go('history')}
      />
      <InlineNotificationList
        title="Late for work"
        count={metrics.late || (lists.late || []).length}
        items={lists.late || []}
        emptyText="No late arrivals recorded today."
        tone="warning"
        renderDetail={(item) => item.status_label || 'Late'}
        actionLabel="Open attendance approvals"
        onOpen={() => go('approvals')}
      />
      <InlineNotificationList
        title="Missing sign-out"
        count={metrics.missing_sign_out || (lists.missing_sign_out || []).length}
        items={lists.missing_sign_out || []}
        emptyText="No missing sign-outs."
        tone="danger"
        renderDetail={() => 'Open session'}
        actionLabel="Open attendance approvals"
        onOpen={() => go('approvals')}
      />
      <InlineNotificationList
        title="Upcoming / current leave"
        count={metrics.approved_leave || approvedLeave.length}
        items={approvedLeave}
        emptyText="No staff currently scheduled for leave."
        tone="info"
        renderDetail={(item) => `${item.leave_start} to ${item.leave_end} · back ${item.return_date}`}
        actionLabel="Open leave module"
        onOpen={() => go('leave')}
      />
      <InlineNotificationList
        title="Pending leave approvals"
        count={metrics.pending_leave || (lists.pending_leave || []).length}
        items={lists.pending_leave || []}
        emptyText="No pending leave applications."
        tone="info"
        renderDetail={(item) => `${item.leave_start || ''}${item.leave_end ? ` to ${item.leave_end}` : ''} · ${item.reason || 'No reason'}`}
        actionLabel="Open leave approvals"
        onOpen={() => go('leave')}
      />
      <InlineNotificationList
        title="GPS / area issues"
        count={(lists.gps_issues || []).length}
        items={lists.gps_issues || []}
        emptyText="No GPS exceptions."
        tone="danger"
        renderDetail={(item) => item.status_label || 'GPS issue'}
        actionLabel="Open attendance approvals"
        onOpen={() => go('approvals')}
      />
    </section>
  )
}

function LeaveList({ title, items = [], emptyText, statusFilter = 'all', onStatusChange }) {
  const filtered = statusFilter === 'all'
    ? items
    : items.filter((item) => String(item.status_code || item.status || '').toLowerCase() === statusFilter)

  return (
    <section className="form-card dashboard-list-card">
      <div className="detail-header">
        <h2>{title}</h2>
        {onStatusChange ? (
          <label className="compact-filter">Approval status
            <select value={statusFilter} onChange={(e) => onStatusChange(e.target.value)}>
              <option value="all">All</option>
              <option value="approved">Approved</option>
              <option value="pending">Pending</option>
              <option value="rejected">Rejected</option>
              <option value="declined">Declined</option>
            </select>
          </label>
        ) : null}
      </div>
      <div className="table-wrap compact-table">
        <table>
          <thead><tr><th>Name</th><th>Leave type</th><th>Approved leave</th><th>Return date</th><th>Status</th><th>Reason</th></tr></thead>
          <tbody>
            {filtered.map((item) => (
              <tr key={`${title}-${item.application_id || item.user_id}`}>
                <td><strong>{item.full_name}</strong><br /><span className="muted">{item.role || item.email || '—'}</span></td>
                <td>{item.leave_type || 'Leave'}</td>
                <td>{item.leave_start || ''}{item.leave_end ? ` to ${item.leave_end}` : ''}</td>
                <td><span className="status-pill approved_leave">{item.return_date || 'After leave'}</span></td>
                <td><span className={`status-pill ${item.status_code || ''}`}>{item.status_label || item.status_code || 'Pending'}</span></td>
                <td>{item.reason || 'No reason supplied'}</td>
              </tr>
            ))}
            {!filtered.length ? <tr><td colSpan="6" className="muted">{emptyText}</td></tr> : null}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function toDateOnly(value) {
  if (!value) return null
  const d = new Date(`${value}T00:00:00`)
  return Number.isNaN(d.getTime()) ? null : d
}

function addDays(date, days) {
  const d = new Date(date)
  d.setDate(d.getDate() + days)
  return d
}

function formatDate(value) {
  if (!value) return '—'
  const d = value instanceof Date ? value : toDateOnly(value)
  if (!d || Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-ZA', { year: 'numeric', month: 'short', day: '2-digit' })
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

function LeaveCalendar({ items = [] }) {
  const approved = items.filter((item) => String(item.status_code || '').toLowerCase() === 'approved')
  return (
    <section className="form-card dashboard-list-card">
      <h2>Leave calendar / staff away</h2>
      <p className="muted">Approved current and upcoming leave for this franchise or manager scope.</p>
      <div className="leave-calendar-strip">
        {approved.map((item) => (
          <div className="leave-calendar-item" key={`calendar-${item.application_id}`}>
            <strong>{item.full_name}</strong>
            <div><div className="leave-bar" /><small>{item.leave_start} to {item.leave_end} · Back {item.return_date}</small></div>
            <span className="status-pill approved">Back {item.return_date}</span>
          </div>
        ))}
        {!approved.length ? <p className="muted">No approved current or upcoming leave found.</p> : null}
      </div>
    </section>
  )
}

export default function OverviewDashboardPage({ onNavigate }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [leaveStatusFilter, setLeaveStatusFilter] = useState('all')
  const [showNotificationHistory, setShowNotificationHistory] = useState(false)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      setData(await getDashboardAlerts())
    } catch (err) {
      setError(err.message || 'Failed to load dashboard alerts')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const readNotification = async (id) => {
    try {
      await markNotificationRead(id)
      load()
    } catch (err) {
      setError(err.message || 'Failed to update notification')
    }
  }

  if (loading && !data) return <div className="form-card"><p>Loading dashboard...</p></div>
  if (error && !data) return <div className="form-card"><p className="error">{error}</p></div>

  const metrics = data?.metrics || {}
  const lists = data?.lists || {}
  const suggestions = data?.suggestions || []
  const notifications = data?.notifications || []
  const unreadNotifications = notifications.filter((n) => !n.is_read)
  const readNotifications = notifications.filter((n) => n.is_read)

  return (
    <div className="overview-dashboard overview-dashboard-pro">
      {error ? <p className="error">{error}</p> : null}

      <OverviewMetricRail metrics={metrics} lists={lists} />

      <OverviewNotifications lists={lists} metrics={metrics} onNavigate={onNavigate} />

      <div className="overview-action-row enterprise-action-stack">
        <section className="form-card suggestions-card">
          <div className="overview-card-title">
            <div>
              <p className="eyebrow">Next actions</p>
              <h2>Smart suggestions</h2>
            </div>
          </div>
          <div className="suggestion-stack">
            {suggestions.length ? suggestions.slice(0, 5).map((s, idx) => (
              <button type="button" className={`suggestion-item suggestion-link ${s.level || ''}`} key={`${s.title}-${idx}`} onClick={() => s.target_tab && onNavigate?.(s.target_tab)}>
                <strong>{s.title}</strong>
                <p>{s.message}</p>
                {s.action ? <small>{s.action}</small> : null}
              </button>
            )) : <p className="muted">No urgent suggestions right now.</p>}
          </div>
        </section>

        <section className="form-card notifications-card">
          <div className="overview-card-title split">
            <div>
              <p className="eyebrow">Outbox</p>
              <h2>Latest notifications</h2>
            </div>
            <div className="button-row"><button className="glass-button small-button" onClick={() => setShowNotificationHistory((value) => !value)}>{showNotificationHistory ? 'Unread' : `History (${readNotifications.length})`}</button><button className="glass-button small-button" onClick={load}>Refresh</button></div>
          </div>
          <div className="notification-stack">
            {(showNotificationHistory ? readNotifications : unreadNotifications).length ? (showNotificationHistory ? readNotifications : unreadNotifications).slice(0, 20).map((n) => (
              <div className={`notification-row ${n.is_read ? 'read' : ''} ${n.severity || ''}`} key={n.id}>
                <button type="button" className="notification-main-button" onClick={() => n.target_tab && onNavigate?.(n.target_tab)}>
                  <strong>{n.subject}</strong>
                  <p>{n.message}</p>
                  <small>{n.created_at ? new Date(n.created_at).toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''} · {n.status || 'pending'}</small>
                </button>
                {!n.is_read ? <button className="link-button" onClick={() => readNotification(n.id)}>Mark read</button> : null}
              </div>
            )) : <p className="muted">{showNotificationHistory ? 'No read notifications in history.' : 'No unread notifications.'}</p>}
          </div>
        </section>
      </div>

      <LeaveReturnTimeline items={lists.approved_leave || []} year={2026} month={4} />

      <div className="overview-detail-grid">
        <LeaveList title="Leave applications" items={lists.leave_applications || lists.approved_leave || []} emptyText="No leave applications found for this scope." statusFilter={leaveStatusFilter} onStatusChange={setLeaveStatusFilter} />
        <LeaveCalendar items={lists.approved_leave || []} />
        <PersonList title="Pending leave applications" items={lists.pending_leave || []} emptyText="No pending leave applications found." />
        <PersonList title="Not signed in today" items={lists.not_signed_in || []} emptyText="Everyone in scope has signed in or no active staff found." />
        <PersonList title="Late arrivals" items={lists.late || []} emptyText="No late arrivals found today." />
        <PersonList title="Missing sign-out" items={lists.missing_sign_out || []} emptyText="No missing sign-outs found." />
        <PersonList title="Outside area / GPS issues" items={lists.gps_issues || []} emptyText="No GPS issues found today." />
      </div>
    </div>
  )
}
