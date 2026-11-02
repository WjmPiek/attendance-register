import { parseApiDateTime } from './dateTime.js'

export function attendanceDay(value) {
  const date = value instanceof Date ? value : parseApiDateTime(value)
  return date && !Number.isNaN(date.getTime()) ? new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Johannesburg', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date) : ''
}

export function formatAttendanceDuration(value) {
  if (value == null) return '—'
  const minutes = Math.max(0, Math.floor(Number(value) || 0)), hours = Math.floor(minutes / 60)
  return hours ? `${hours}h ${minutes % 60}m` : `${minutes} min`
}

export function buildAttendanceHistory(events, sessions, now = new Date()) {
  const realSessions = sessions.filter(session => session.status !== 'no_attendance')
  const byEvent = new Map()
  for (const session of realSessions) for (const id of [session.sign_in_event_id, session.sign_out_event_id]) if (id != null) byEvent.set(String(id), session)
  const uniqueEvents = [...new Map(events.map(event => [String(event.id), event])).values()]
  const ids = new Set(uniqueEvents.map(event => String(event.id)))
  const represented = new Set()
  const records = uniqueEvents.map(event => {
    const match = byEvent.get(String(event.id)), session = match && Number(match.user_id) === Number(event.user_id) ? match : null
    if (session) represented.add(session.session_id)
    const duration = session && (String(event.id) === String(session.sign_out_event_id) || (!ids.has(String(session.sign_out_event_id)) && String(event.id) === String(session.sign_in_event_id))) ? session.duration_minutes : null
    return { ...event, session, duration_minutes: duration, contextOnly: false }
  })
  // The sessions API can include an open sign-in before the date window. Keep
  // that information, but label it as session context rather than inventing an event.
  for (const session of realSessions) if (!represented.has(session.session_id)) records.push({ ...session,
    id: `context-${session.session_id}`, created_at: session.sign_in_at || session.sign_out_at,
    action: 'session_context', session, duration_minutes: session.duration_minutes,
    contextOnly: true, map_url: session.sign_out_map_url || session.sign_in_map_url })
  records.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  const missing = row => !!(row.missing_sign_out || (row.action !== 'sign_out' && row.session?.missing_sign_out))
  const late = row => !!(row.is_late || (row.action !== 'sign_out' && row.session?.is_late))
  const early = row => !!(row.left_early || (row.action === 'sign_out' && row.session?.left_early))
  const today = attendanceDay(now)
  const todaySessions = realSessions.filter(session => attendanceDay(session.sign_in_at || session.sign_out_at) === today)
  const todayEvents = records.filter(row => !row.contextOnly && attendanceDay(row.created_at) === today)
  const latest = todayEvents[0]
  const sessionRecords = selected => { const keys = new Set(selected.map(row => row.session_id)); return records.filter(row => row.session && keys.has(row.session.session_id)) }
  const minutes = selected => selected.reduce((sum, session) => sum + Number(session.duration_minutes || 0), 0)
  const sessionMetric = (key, label, selected, value = selected.length) => ({ key, label, value, count: selected.length, rows: sessionRecords(selected), unit: 'sessions' })
  const eventMetric = (key, label, predicate) => { const rows = records.filter(predicate); return { key, label, value: rows.length, count: rows.length, rows, unit: 'records' } }
  const todayMetrics = [
    sessionMetric('today-sessions', 'Sessions today', todaySessions),
    sessionMetric('today-time', 'Session time today', todaySessions, formatAttendanceDuration(minutes(todaySessions))),
    { key: 'latest-status', label: 'Latest status today', value: latest ? latest.action === 'sign_in' ? 'Signed in' : latest.action === 'sign_out' ? 'Signed out' : String(latest.attendance_status || latest.action).replaceAll('_', ' ') : 'No events', rows: latest ? [latest] : [], count: latest ? 1 : 0, unit: 'events' },
  ]
  const metrics = [
    sessionMetric('sessions', 'Sessions', realSessions),
    sessionMetric('completed', 'Completed sessions', realSessions.filter(row => row.sign_in_at && row.sign_out_at)),
    sessionMetric('signed-in', 'Currently signed in', realSessions.filter(row => row.sign_in_at && !row.sign_out_at && !row.missing_sign_out)),
    sessionMetric('duration', 'Total session time', realSessions, formatAttendanceDuration(minutes(realSessions))),
    eventMetric('late', 'Late arrivals', late), eventMetric('early-leave', 'Early departures', early),
    eventMetric('outside-gps', 'Outside office GPS', row => row.gps_status === 'outside_area'),
    eventMetric('low-accuracy', 'Low GPS accuracy', row => row.gps_status === 'accuracy_too_low'),
    eventMetric('missing-sign-out', 'Missing sign-out', missing),
  ]
  return { records, realSessions, todayMetrics, metrics }
}
