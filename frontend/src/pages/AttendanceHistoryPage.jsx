import { useEffect, useMemo, useState } from 'react'
import Card from '../components/Card'
import { exportAttendancePdf, exportAttendancePdfBatch, getAttendanceFranchises, getAttendanceHistory, getAttendanceSessions, getAttendanceVisibleUsers } from '../api/client'

function statusClass(value) {
  if (value === 'no_attendance') return 'badge neutral'
  if (['present', 'signed_out', 'inside_area', 'complete'].includes(value)) return 'badge good'
  if (['late', 'early_leave', 'accuracy_too_low', 'open'].includes(value)) return 'badge warn'
  return 'badge bad'
}

function eventStatus(row) {
  if (row.missing_sign_out) return 'missing_sign_out'
  return row.attendance_status || row.gps_status || 'recorded'
}

function formatTime(value) {
  if (!value) return 'n/a'
  return new Date(value).toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function formatDuration(minutes) {
  if (minutes === null || minutes === undefined) return 'n/a'
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  if (!hours) return `${mins} min`
  return `${hours}h ${mins}m`
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function todayKey() {
  return new Date().toISOString().slice(0, 10)
}

function userDisplay(row) {
  const name = row.user_full_name || [row.user_name, row.user_surname].filter(Boolean).join(' ')
  const detail = row.user_role || row.user_staff_type || row.user_email
  return {
    name: name || `User #${row.user_id}`,
    detail,
  }
}

function UserCell({ row }) {
  const user = userDisplay(row)
  return (
    <div className="user-display-cell">
      <strong>{user.name}</strong>
      <span>{user.detail || `User ID ${row.user_id}`}</span>
    </div>
  )
}

export default function AttendanceHistoryPage({ me }) {
  const isManagerView = me.roles.includes('SuperUser') || me.roles.includes('FranchiseUser') || me.roles.includes('ManagerUser')
  const [events, setEvents] = useState([])
  const [sessions, setSessions] = useState([])
  const [sessionSummary, setSessionSummary] = useState(null)
  const [filters, setFilters] = useState({ userId: '', franchiseId: '', fromDate: '', toDate: '' })
  const [tab, setTab] = useState('sessions')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [visibleUsers, setVisibleUsers] = useState([])
  const [exportUserIds, setExportUserIds] = useState([])
  const [franchises, setFranchises] = useState([])
  const [exportMode, setExportMode] = useState(null)

  const activeFilters = useMemo(() => ({
    userId: isManagerView ? filters.userId : '',
    franchiseId: isManagerView ? filters.franchiseId : '',
    fromDate: filters.fromDate,
    toDate: filters.toDate,
  }), [filters, isManagerView])

  const loadAll = async () => {
    setLoading(true)
    setError('')
    try {
      const [eventData, sessionData, userData, franchiseData] = await Promise.all([
        getAttendanceHistory(activeFilters),
        getAttendanceSessions(activeFilters),
        isManagerView ? getAttendanceVisibleUsers(activeFilters.franchiseId) : Promise.resolve({ items: [] }),
        isManagerView ? getAttendanceFranchises() : Promise.resolve({ items: [] }),
      ])
      setEvents(eventData.items || [])
      setSessions(sessionData.items || [])
      setSessionSummary(sessionData.summary || null)
      if (isManagerView) {
        setVisibleUsers(userData.items || [])
        setFranchises(franchiseData.items || [])
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.userId, filters.franchiseId, filters.fromDate, filters.toDate])

  const eventSummary = useMemo(() => {
    return events.reduce(
      (acc, row) => {
        acc.total += 1
        if (row.action === 'sign_in') acc.signIns += 1
        if (row.action === 'sign_out') acc.signOuts += 1
        if (row.is_late) acc.late += 1
        if (row.left_early) acc.early += 1
        if (row.missing_sign_out) acc.missing += 1
        if (row.gps_status === 'outside_area') acc.outside += 1
        if (row.gps_status === 'accuracy_too_low') acc.lowAccuracy += 1
        return acc
      },
      { total: 0, signIns: 0, signOuts: 0, late: 0, early: 0, missing: 0, outside: 0, lowAccuracy: 0 }
    )
  }, [events])

  const todaySummary = useMemo(() => {
    const today = todayKey()
    const todaySessions = sessions.filter((row) => (row.sign_in_at || row.sign_out_at || '').slice(0, 10) === today)
    const latest = todaySessions[0]
    const minutes = todaySessions.reduce((sum, row) => sum + (row.duration_minutes || 0), 0)
    return { count: todaySessions.length, minutes, latest }
  }, [sessions])

  const mapRows = useMemo(() => {
    return events.filter((row) => row.map_url).slice(0, 50)
  }, [events])

  const handleExport = async (view) => {
    try {
      const selectedIds = exportUserIds.length ? exportUserIds : [activeFilters.userId || String(me.id)]
      const stamp = new Date().toISOString().slice(0, 10)
      if (selectedIds.length === 1) {
        const userId = selectedIds[0]
        const blob = await exportAttendancePdf({ view, ...activeFilters, userId })
        downloadBlob(blob, `attendance_${view}_user_${userId}_${stamp}.pdf`)
      } else {
        const blob = await exportAttendancePdfBatch({ view, fromDate: activeFilters.fromDate, toDate: activeFilters.toDate, userIds: selectedIds })
        downloadBlob(blob, `attendance_${view}_selected_users_${stamp}.zip`)
      }
    } catch (err) {
      setError(err.message)
    }
  }

  const toggleExportUser = (userId) => {
    const id = String(userId)
    setExportUserIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])
  }

  const selectedUserLabel = (id) => {
    const match = visibleUsers.find((user) => String(user.user_id) === String(id))
    return match ? match.label : `User #${id}`
  }

  return (
    <Card title="Attendance History">
      <div className="history-toolbar">
        {isManagerView ? (
          <>
            {me.roles.includes('SuperUser') ? (
              <label>
                View franchise
                <select
                  value={filters.franchiseId}
                  onChange={(event) => {
                    setFilters({ ...filters, franchiseId: event.target.value, userId: '' })
                    setExportUserIds([])
                    setExportMode(null)
                  }}
                >
                  <option value="">All approved franchises / all users</option>
                  {franchises.map((franchise, index) => (
                    <option key={`${franchise.franchise_id || 'registration'}-${index}`} value={franchise.franchise_id || ''} disabled={!franchise.franchise_id}>
                      {franchise.label}{franchise.status ? ` (${franchise.status})` : ''}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <label>
              View user by name
              <select
                value={filters.userId}
                onChange={(event) => {
                  setFilters({ ...filters, userId: event.target.value })
                  setExportUserIds([])
                  setExportMode(null)
                }}
              >
                <option value="">All users in selected franchise/scope</option>
                {visibleUsers.map((user) => (
                  <option key={user.user_id} value={user.user_id}>{user.label}{user.detail ? ` - ${user.detail}` : ''}</option>
                ))}
              </select>
            </label>
          </>
        ) : null}
        <label>
          From
          <input
            type="date"
            value={filters.fromDate}
            onChange={(event) => setFilters({ ...filters, fromDate: event.target.value })}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={filters.toDate}
            onChange={(event) => setFilters({ ...filters, toDate: event.target.value })}
          />
        </label>
        <button onClick={loadAll} disabled={loading}>{loading ? 'Loading...' : 'Refresh'}</button>
      </div>
      <p className="muted small">Select a franchise to view everyone under it, then optionally filter by one user. Export selection appears only after clicking an export button.</p>

      {isManagerView && exportMode ? (
        <div className="export-user-panel">
          <div className="export-user-panel-head">
            <strong>Export {exportMode} PDF files</strong>
            <div className="button-row compact">
              <button className="secondary" type="button" onClick={() => setExportUserIds(visibleUsers.map((user) => String(user.user_id)))}>Select all</button>
              <button className="secondary" type="button" onClick={() => setExportUserIds([])}>Clear</button>
              <button type="button" onClick={() => handleExport(exportMode)}>Download {exportMode} PDF</button>
              <button className="secondary" type="button" onClick={() => setExportMode(null)}>Cancel</button>
            </div>
          </div>
          <div className="export-user-list">
            {visibleUsers.map((user) => (
              <label className="user-check" key={user.user_id}>
                <input type="checkbox" checked={exportUserIds.includes(String(user.user_id))} onChange={() => toggleExportUser(user.user_id)} />
                <span><strong>{user.label}</strong>{user.detail ? <small>{user.detail}</small> : null}</span>
              </label>
            ))}
          </div>
          <p className="muted small">Selected for export: {exportUserIds.length ? exportUserIds.map(selectedUserLabel).join(', ') : selectedUserLabel(activeFilters.userId || me.id)}</p>
        </div>
      ) : null}

      <div className="button-row">
        <button className={tab === 'sessions' ? 'secondary active' : 'secondary'} onClick={() => setTab('sessions')}>Sessions</button>
        <button className={tab === 'events' ? 'secondary active' : 'secondary'} onClick={() => setTab('events')}>Events</button>
        <button className={tab === 'map' ? 'secondary active' : 'secondary'} onClick={() => setTab('map')}>Map</button>
        <button className="secondary" onClick={() => isManagerView ? setExportMode('sessions') : handleExport('sessions')}>Export sessions PDF</button>
        <button className="secondary" onClick={() => isManagerView ? setExportMode('events') : handleExport('events')}>Export events PDF</button>
      </div>

      <div className="today-card">
        <h4>Today summary</h4>
        <div className="today-grid">
          <div><strong>{todaySummary.count}</strong><span>Sessions today</span></div>
          <div><strong>{formatDuration(todaySummary.minutes)}</strong><span>Total time</span></div>
          <div><strong>{todaySummary.latest?.status || 'n/a'}</strong><span>Latest status</span></div>
        </div>
      </div>

      <div className="summary-grid">
        <div><strong>{sessionSummary?.total_sessions || 0}</strong><span>Sessions</span></div>
        <div><strong>{sessionSummary?.completed_sessions || 0}</strong><span>Completed</span></div>
        <div><strong>{formatDuration(sessionSummary?.total_minutes || 0)}</strong><span>Total duration</span></div>
        <div><strong>{sessionSummary?.late_sessions || 0}</strong><span>Late</span></div>
        <div><strong>{sessionSummary?.early_leave_sessions || 0}</strong><span>Early leave</span></div>
        <div><strong>{sessionSummary?.outside_area || 0}</strong><span>Outside area</span></div>
        <div><strong>{sessionSummary?.low_accuracy || 0}</strong><span>Low accuracy</span></div>
        <div><strong>{sessionSummary?.missing_sign_out || 0}</strong><span>Missing sign-out</span></div>
      </div>

      {error ? <p className="error">{error}</p> : null}

      {tab === 'sessions' ? (
        <div className="table-wrap">
          <table className="history-table">
            <thead>
              <tr>
                <th>Sign in</th>
                <th>Sign out</th>
                <th>User</th>
                <th>Duration</th>
                <th>Status</th>
                <th>Rules</th>
                <th>Maps</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((row) => (
                <tr key={row.session_id} className={`status-row status-${row.status}`}>
                  <td>{formatTime(row.sign_in_at)}</td>
                  <td>{formatTime(row.sign_out_at)}</td>
                  <td><UserCell row={row} /></td>
                  <td>{formatDuration(row.duration_minutes)}</td>
                  <td><span className={statusClass(row.status)}>{row.status}</span></td>
                  <td>
                    {row.is_late ? <div>Late: {row.late_minutes} min</div> : null}
                    {row.left_early ? <div>Early: {row.early_leave_minutes} min</div> : null}
                    {row.missing_sign_out ? <div>Missing sign-out</div> : null}
                    {row.status === 'no_attendance' ? <span className="muted">No attendance recorded</span> : (!row.is_late && !row.left_early && !row.missing_sign_out ? <span className="muted">OK</span> : null)}
                  </td>
                  <td>
                    {row.status === 'no_attendance' ? <span className="muted">n/a</span> : (row.sign_in_map_url ? <a href={row.sign_in_map_url} target="_blank" rel="noreferrer">In</a> : <span className="muted">In n/a</span>)}
                    {row.status === 'no_attendance' ? null : <> / {row.sign_out_map_url ? <a href={row.sign_out_map_url} target="_blank" rel="noreferrer">Out</a> : <span className="muted">Out n/a</span>}</>}
                  </td>
                </tr>
              ))}
              {!sessions.length ? <tr><td colSpan="7" className="muted">No sessions found.</td></tr> : null}
            </tbody>
          </table>
        </div>
      ) : null}

      {tab === 'events' ? (
        <div className="table-wrap">
          <table className="history-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>User</th>
                <th>Action</th>
                <th>Status</th>
                <th>GPS</th>
                <th>Rules</th>
                <th>Map</th>
              </tr>
            </thead>
            <tbody>
              {events.map((row) => {
                const status = eventStatus(row)
                return (
                  <tr key={row.id} className={`status-row status-${status}`}>
                    <td>{formatTime(row.created_at)}</td>
                    <td><UserCell row={row} /></td>
                    <td>{row.action}</td>
                    <td><span className={statusClass(status)}>{status}</span></td>
                    <td>
                      <div>{row.gps_status || 'n/a'}</div>
                      <div className="muted small">{row.distance_from_site_m == null ? 'No distance' : `${Math.round(row.distance_from_site_m)} m`}</div>
                      <div className="muted small">Accuracy: {row.accuracy_meters || 'n/a'}</div>
                    </td>
                    <td>
                      {row.is_late ? <div>Late: {row.late_minutes} min</div> : null}
                      {row.left_early ? <div>Early: {row.early_leave_minutes} min</div> : null}
                      {row.missing_sign_out ? <div>Missing sign-out</div> : null}
                      {!row.is_late && !row.left_early && !row.missing_sign_out ? <span className="muted">OK</span> : null}
                    </td>
                    <td>{row.map_url ? <a href={row.map_url} target="_blank" rel="noreferrer">Open map</a> : <span className="muted">n/a</span>}</td>
                  </tr>
                )
              })}
              {!events.length ? <tr><td colSpan="7" className="muted">No attendance events found.</td></tr> : null}
            </tbody>
          </table>
        </div>
      ) : null}

      {tab === 'map' ? (
        <div className="map-grid">
          {mapRows.map((row) => (
            <a className="map-card" href={row.map_url} target="_blank" rel="noreferrer" key={row.id}>
              <strong>{row.action} - {userDisplay(row).name}</strong>
              <span>{formatTime(row.created_at)}</span>
              <span>{row.latitude}, {row.longitude}</span>
              <span className={statusClass(eventStatus(row))}>{eventStatus(row)}</span>
            </a>
          ))}
          {!mapRows.length ? <p className="muted">No GPS locations available for the current filter.</p> : null}
        </div>
      ) : null}
    </Card>
  )
}
