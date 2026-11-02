import { useEffect, useMemo, useRef, useState } from 'react'
import Card from '../components/Card'
import { buildAttendanceHistory, formatAttendanceDuration } from '../utils/attendanceHistory'
import './AttendanceHistoryPage.css'
import { exportAttendancePdf, exportAttendancePdfBatch, getAttendanceEventPhoto, getAttendanceFranchises, getAttendanceHistory, getAttendanceSessions, getAttendanceVisibleUsers } from '../api/client'
import { formatJohannesburgDateTime } from '../utils/dateTime'

function statusClass(value) {
  if (value === 'no_attendance') return 'badge neutral'
  if (['present', 'signed_out', 'inside_area', 'complete'].includes(value)) return 'badge good'
  if (['late', 'early_leave', 'accuracy_too_low', 'open', 'on_road'].includes(value)) return 'badge warn'
  return 'badge bad'
}

function eventStatus(row) {
  if (row.missing_sign_out || (row.action !== 'sign_out' && row.session?.missing_sign_out)) return 'missing_sign_out'
  if (row.contextOnly) return row.session?.status || 'open'
  return row.attendance_status || row.gps_status || 'recorded'
}

function gpsStatusLabel(value) {
  const labels = {
    inside_area: 'Inside office GPS range',
    outside_area: 'Not in office GPS range',
    accuracy_too_low: 'GPS accuracy too low',
    no_allocation: 'Office GPS allocation missing',
    on_road: 'On-road attendance',
  }
  return labels[value] || String(value || 'Not available').replaceAll('_', ' ')
}

function attendanceStatusLabel(value) {
  if (value === 'outside_area') return 'Not in office GPS range'
  if (value === 'accuracy_too_low') return 'GPS accuracy too low'
  return String(value || 'recorded').replaceAll('_', ' ')
}

function formatTime(value) {
  return formatJohannesburgDateTime(value)
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

function readHistoryLocation() {
  const query = new URLSearchParams(typeof window === 'undefined' ? '' : window.location.search)
  return { detail: query.get('history_detail') || '', filters: {
    userId: query.get('history_user') || '', franchiseId: query.get('history_franchise') || '',
    fromDate: query.get('history_from') || '', toDate: query.get('history_to') || '',
  } }
}

function AttendanceRecords({ records, loading, openPhoto }) {
  return <div className="table-wrap"><table className="history-table attendance-events-table">
    <thead><tr><th>Time</th><th>Manager / employee</th><th>Action</th><th>Time signed in</th><th>Status</th><th>GPS</th><th>Rules</th><th>Evidence</th><th>Location</th></tr></thead>
    <tbody>{records.map(row => {
      const status = eventStatus(row), session = row.session
      const late = row.is_late || (row.action !== 'sign_out' && session?.is_late)
      const early = row.left_early || (row.action === 'sign_out' && session?.left_early)
      const missing = row.missing_sign_out || (row.action !== 'sign_out' && session?.missing_sign_out)
      return <tr key={row.id} className={`status-row status-${status}`}>
        <td>{formatTime(row.created_at)}{row.contextOnly && <small className="history-context-note">Earlier attendance carried forward</small>}</td>
        <td><UserCell row={row}/></td>
        <td>{row.contextOnly ? 'Carried-forward attendance' : row.action === 'sign_in' ? 'Sign in' : row.action === 'sign_out' ? 'Sign out' : row.action}</td>
        <td>{formatAttendanceDuration(row.duration_minutes)}{session && !session.sign_out_at && !session.missing_sign_out && <small className="history-context-note">Still signed in</small>}{session && !session.sign_in_at && <small className="history-context-note">Sign-in not recorded</small>}</td>
        <td><span className={statusClass(status)}>{attendanceStatusLabel(status)}</span></td>
        <td><strong>{gpsStatusLabel(row.gps_status)}</strong>
          {!row.contextOnly && <><div className="muted small">{row.distance_from_site_m == null ? 'Distance unavailable' : `${Math.round(row.distance_from_site_m)} m from office`}</div><div className="muted small">Accuracy: {row.accuracy_meters == null ? 'n/a' : `${row.accuracy_meters} m`}</div></>}
        </td>
        <td>{late && <div>Late: {row.late_minutes || session?.late_minutes || 0} min</div>}{early && <div>Early: {row.early_leave_minutes || session?.early_leave_minutes || 0} min</div>}{missing && <div>Missing sign-out</div>}{!late && !early && !missing && <span className="muted">OK</span>}</td>
        <td>{row.contextOnly ? <span className="muted">View the original event date for evidence.</span> : <><div>Signature: {row.signature_status || 'n/a'}</div><div>Photo: {row.photo_status || 'not available'}</div>{row.photo_status === 'captured' && <button type="button" className="glass-button small-button" onClick={() => openPhoto(row.id)}>View photo</button>}</>}</td>
        <td>{row.map_url ? <a href={row.map_url} target="_blank" rel="noreferrer">Open map</a> : <span className="muted">Not available</span>}</td>
      </tr>
    })}{!records.length && <tr><td colSpan="9" className="muted">{loading ? 'Loading attendance…' : 'No matching attendance records.'}</td></tr>}</tbody>
  </table></div>
}

export default function AttendanceHistoryPage({ me }) {
  const isManagerView = me.roles.some(role => ['SuperUser', 'FranchiseUser', 'ManagerUser'].includes(role))
  const [events, setEvents] = useState([]), [sessions, setSessions] = useState([])
  const [filters, setFilters] = useState(() => readHistoryLocation().filters), [detailKey, setDetailKey] = useState(() => readHistoryLocation().detail)
  const [visibleUsers, setVisibleUsers] = useState([]), [franchises, setFranchises] = useState([])
  const [loading, setLoading] = useState(true), [error, setError] = useState('')
  const [exportOpen, setExportOpen] = useState(false), [exportView, setExportView] = useState('events'), [exportUserIds, setExportUserIds] = useState([]), [exporting, setExporting] = useState(false)
  const request = useRef(0)
  const activeFilters = useMemo(() => ({ userId: detailKey && isManagerView ? filters.userId : '', franchiseId: detailKey && isManagerView ? filters.franchiseId : '', fromDate: detailKey ? filters.fromDate : '', toDate: detailKey ? filters.toDate : '' }), [filters, isManagerView, detailKey])
  const model = useMemo(() => buildAttendanceHistory(events, sessions), [events, sessions])
  const detail = [...model.todayMetrics, ...model.metrics].find(metric => metric.key === detailKey)
  const loadAll = async () => {
    const id = ++request.current
    setLoading(true); setError(''); setEvents([]); setSessions([])
    if (activeFilters.fromDate && activeFilters.toDate && activeFilters.fromDate > activeFilters.toDate) { setError('The end date must be on or after the start date.'); setLoading(false); return }
    try {
      const [eventData, sessionData, users, franchiseData] = await Promise.all([
        getAttendanceHistory(activeFilters), getAttendanceSessions(activeFilters),
        isManagerView ? getAttendanceVisibleUsers(activeFilters.franchiseId) : Promise.resolve({ items: [] }),
        me.roles.includes('SuperUser') ? getAttendanceFranchises() : Promise.resolve({ items: [] }),
      ])
      if (id !== request.current) return
      setEvents(eventData.items || []); setSessions(sessionData.items || []); setVisibleUsers(users.items || []); setFranchises(franchiseData.items || [])
    } catch (err) { if (id === request.current) setError(err.message) }
    finally { if (id === request.current) setLoading(false) }
  }
  useEffect(() => { loadAll(); return () => { request.current += 1 } }, [activeFilters.userId, activeFilters.franchiseId, activeFilters.fromDate, activeFilters.toDate])
  useEffect(() => {
    const sync = () => { const location = readHistoryLocation(); setDetailKey(location.detail); setFilters(location.filters) }
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [])
  const locationUrl = (key, nextFilters = filters) => {
    const url = new URL(window.location.href); url.searchParams.set('tab', 'history')
    for (const [name, value] of Object.entries({ history_detail: key, history_user: nextFilters.userId, history_franchise: nextFilters.franchiseId, history_from: nextFilters.fromDate, history_to: nextFilters.toDate })) {
      if (value) url.searchParams.set(name, value); else url.searchParams.delete(name)
    }
    return url
  }
  const updateFilters = changes => {
    const next = { ...filters, ...changes }
    setFilters(next); setExportUserIds([]); setExportOpen(false)
    window.history.replaceState({}, '', locationUrl(detailKey, next))
  }
  const navigate = key => { const next = key ? filters : { userId:'', franchiseId:'', fromDate:'', toDate:'' }; window.history.pushState({}, '', locationUrl(key, next)); setFilters(next); setDetailKey(key); setExportOpen(false); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  const openPhoto = async id => {
    try {
      const blob = await getAttendanceEventPhoto(id), url = URL.createObjectURL(blob), link = document.createElement('a')
      link.href = url; link.target = '_blank'; link.rel = 'noopener'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (err) { setError(err.message || 'Attendance photo could not be opened.') }
  }
  const handleExport = async () => {
    setExporting(true); setError('')
    try {
      const recordIds = [...new Set([...events, ...model.realSessions].map(row => String(row.user_id)))]
      const selectedIds = exportUserIds.length ? exportUserIds : activeFilters.userId ? [String(activeFilters.userId)] : recordIds.length ? recordIds : [String(me.id)]
      const stamp = new Date(Date.now() + 7200000).toISOString().slice(0, 10)
      if (selectedIds.length === 1) downloadBlob(await exportAttendancePdf({ view: exportView, ...activeFilters, userId: selectedIds[0] }), `attendance_${exportView}_${stamp}.pdf`)
      else downloadBlob(await exportAttendancePdfBatch({ view: exportView, fromDate: activeFilters.fromDate, toDate: activeFilters.toDate, userIds: selectedIds }), `attendance_${exportView}_${stamp}.zip`)
    } catch (err) { setError(err.message) }
    finally { setExporting(false) }
  }
  const metricCard = metric => <a key={metric.key} className="history-metric-card" href={typeof window === 'undefined' ? '#' : locationUrl(metric.key).toString()} onClick={event => { if (!event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) { event.preventDefault(); navigate(metric.key) } }}>
    <h4 className="history-metric-title">{metric.label}</h4><span>{loading ? '…' : metric.value}</span><small className="history-metric-description">{metric.description}</small><small>View records →</small>
  </a>
  const filterPanel = <>
    <div className={`attendance-history-filters${me.roles.includes('SuperUser') ? ' with-franchise' : ''}`}>
      {me.roles.includes('SuperUser') && <label>Franchise<select value={filters.franchiseId} onChange={event => updateFilters({ franchiseId: event.target.value, userId: '' })}><option value="">All approved franchises</option>{franchises.map((franchise, index) => <option key={`${franchise.franchise_id}-${index}`} value={franchise.franchise_id || ''} disabled={!franchise.franchise_id}>{franchise.label}{franchise.status ? ` (${franchise.status})` : ''}</option>)}</select></label>}
      {isManagerView && <label>Manager / employee<select value={filters.userId} onChange={event => updateFilters({ userId: event.target.value })}><option value="">All staff in scope</option>{visibleUsers.map(user => <option key={user.user_id} value={user.user_id}>{user.label}{user.detail ? ` — ${user.detail}` : ''}</option>)}</select></label>}
      <label>From<input type="date" value={filters.fromDate} onChange={event => updateFilters({ fromDate: event.target.value })}/></label>
      <label>To<input type="date" value={filters.toDate} onChange={event => updateFilters({ toDate: event.target.value })}/></label>
    </div>
    <div className="attendance-history-actions"><button type="button" onClick={() => loadAll()} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button><button type="button" className="glass-button" onClick={() => setExportOpen(value => !value)}>Export attendance PDF</button></div>
    {exportOpen && <section className="history-export-panel"><h4>Export attendance</h4><label>Report contents<select value={exportView} onChange={event => setExportView(event.target.value)}><option value="events">Attendance events — full details</option><option value="sessions">Time between sign-in and sign-out</option></select></label><p className="muted">Uses the staff and date filters above. Multiple staff members download as a ZIP of individual PDFs.</p>
      {isManagerView && <><div className="attendance-history-actions"><button type="button" className="glass-button" onClick={() => setExportUserIds(visibleUsers.map(user => String(user.user_id)))}>Select all staff</button><button type="button" className="glass-button" onClick={() => setExportUserIds([])}>Clear selection</button></div><div className="history-export-users">{visibleUsers.map(user => <label key={user.user_id}><input type="checkbox" checked={exportUserIds.includes(String(user.user_id))} onChange={() => setExportUserIds(ids => ids.includes(String(user.user_id)) ? ids.filter(id => id !== String(user.user_id)) : [...ids, String(user.user_id)])}/><span>{user.label}{user.detail && <small>{user.detail}</small>}</span></label>)}</div><p className="muted">{exportUserIds.length ? `${exportUserIds.length} staff selected.` : 'No individual selection: exports the current staff/date scope.'}</p></>}
      <div className="attendance-history-actions"><button type="button" disabled={exporting || loading} onClick={handleExport}>{exporting ? 'Preparing…' : 'Download PDF'}</button><button type="button" className="glass-button" onClick={() => setExportOpen(false)}>Close</button></div>
    </section>}
  </>
  if (detail) return <Card title={detail.label} className="attendance-history-page attendance-history-detail">
    <button type="button" className="glass-button history-back" onClick={() => navigate('')}>← Attendance history</button>
    {filterPanel}
    <p>{detail.description}</p>
    <p className="muted">{filters.fromDate || 'All dates'}{filters.toDate ? ` to ${filters.toDate}` : ''}{filters.userId ? ` · ${visibleUsers.find(user => String(user.user_id) === filters.userId)?.label || 'Selected staff member'}` : ' · Current staff scope'}</p>
    {!loading && !error && <p>{typeof detail.value === 'string' && <><strong>{detail.value}</strong> · </>}{detail.count} {detail.unit}{detail.sessionBased && ` · ${detail.rows.filter(row => !row.contextOnly).length} attendance events`}</p>}
    {error && <p role="alert" className="error-message">{error}</p>}
    <AttendanceRecords records={detail.rows} loading={loading} openPhoto={openPhoto}/>
  </Card>
  return <Card title="Attendance History" className="attendance-history-page">
    {error && <p role="alert" className="error-message">{error}</p>}
    <section className="history-summary-section"><h4>Today</h4><div className="history-metric-grid">{model.todayMetrics.map(metricCard)}</div></section>
    <section className="history-summary-section"><h4>Attendance overview</h4><div className="history-metric-grid">{model.metrics.map(metricCard)}</div></section>
  </Card>
}

