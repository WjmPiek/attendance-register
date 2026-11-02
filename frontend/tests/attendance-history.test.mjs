import test from 'node:test'
import assert from 'node:assert/strict'
import { buildAttendanceHistory, attendanceDay } from '../src/utils/attendanceHistory.js'

const inside = { user_id: 11, gps_status: 'inside_area', signature_status: 'captured', photo_status: 'captured', map_url: 'https://maps.example/location' }
const events = [
  { ...inside, id: 1, action: 'sign_in', created_at: '2026-11-02T06:00:00Z', is_late: true, late_minutes: 5 },
  { ...inside, id: 2, action: 'sign_out', created_at: '2026-11-02T15:00:00Z', left_early: true, early_leave_minutes: 10 },
]
const complete = { session_id: 's1', user_id: 11, sign_in_event_id: 1, sign_out_event_id: 2, sign_in_at: events[0].created_at, sign_out_at: events[1].created_at, duration_minutes: 540, status: 'complete', is_late: true, left_early: true }
const now = new Date('2026-11-02T16:00:00Z')
const metric = (model, key) => [...model.metrics, ...model.todayMetrics].find(item => item.key === key)

test('events keep original evidence and duration appears once on sign-out', () => {
  const model = buildAttendanceHistory(events, [complete], now)
  assert.equal(model.records.length, 2)
  assert.equal(model.records.find(row => row.id === 1).duration_minutes, null)
  assert.equal(model.records.find(row => row.id === 2).duration_minutes, 540)
  for (const row of model.records) {
    assert.equal(row.photo_status, 'captured')
    assert.equal(row.signature_status, 'captured')
    assert.equal(row.map_url, inside.map_url)
    assert.equal(row.gps_status, 'inside_area')
  }
  assert.equal(metric(model, 'completed').count, 1)
  assert.deepEqual(metric(model, 'completed').rows.map(row => row.id).sort(), [1, 2])
  assert.equal(metric(model, 'duration').value, '9h 0m')
})

test('each event ID appears once while different events at the same time survive', () => {
  const extra = { ...events[0], id: 3, action: 'other_action' }
  const model = buildAttendanceHistory([...events, events[0], extra], [complete], now)
  assert.equal(model.records.length, 3)
  assert.equal(model.records.filter(row => row.id === 1).length, 1)
  assert.ok(model.records.some(row => row.id === 3 && row.action === 'other_action'))
})

test('late and early cards show only the relevant event, not the entire pair twice', () => {
  const model = buildAttendanceHistory(events, [complete], now)
  assert.deepEqual(metric(model, 'late').rows.map(row => row.id), [1])
  assert.deepEqual(metric(model, 'early-leave').rows.map(row => row.id), [2])
})

test('prior missing sign-out is labelled context and excluded from currently signed in', () => {
  const stale = { session_id: 'old', user_id: 12, sign_in_event_id: 99, sign_out_event_id: null, sign_in_at: '2026-10-15T06:00:00Z', sign_out_at: null, missing_sign_out: true, status: 'missing_sign_out', sign_in_map_url: 'https://maps.example/old' }
  const model = buildAttendanceHistory(events, [complete, stale, { session_id: 'none', user_id: 13, status: 'no_attendance' }], now)
  assert.equal(metric(model, 'sessions').count, 2)
  assert.equal(metric(model, 'signed-in').count, 0)
  assert.equal(metric(model, 'missing-sign-out').count, 1)
  const row = metric(model, 'missing-sign-out').rows[0]
  assert.equal(row.contextOnly, true)
  assert.equal(row.map_url, stale.sign_in_map_url)
  assert.equal(model.records.filter(item => !item.contextOnly).length, events.length)
})

test('an open session has a working card and remains distinct from missing sign-out', () => {
  const open = { session_id: 'open', user_id: 11, sign_in_event_id: 1, sign_in_at: events[0].created_at, sign_out_at: null, status: 'open', missing_sign_out: false }
  const model = buildAttendanceHistory([events[0]], [open], now)
  assert.equal(metric(model, 'signed-in').count, 1)
  assert.equal(metric(model, 'missing-sign-out').count, 0)
  assert.deepEqual(metric(model, 'signed-in').rows.map(row => row.id), [1])
})

test('unpaired GPS events are retained and reachable through their cards', () => {
  const outside = { ...inside, id: 9, action: 'sign_out', gps_status: 'outside_area', created_at: events[0].created_at }
  const inaccurate = { ...outside, id: 10, gps_status: 'accuracy_too_low' }
  const model = buildAttendanceHistory([outside, inaccurate], [], now)
  assert.equal(model.records.length, 2)
  assert.deepEqual(metric(model, 'outside-gps').rows.map(row => row.id), [9])
  assert.deepEqual(metric(model, 'low-accuracy').rows.map(row => row.id), [10])
})

test('events are never paired with a different staff member', () => {
  const model = buildAttendanceHistory(events, [{ ...complete, user_id: 88 }], now)
  assert.equal(model.records.find(row => row.id === 1).session, null)
  assert.equal(model.records.find(row => row.id === 2).duration_minutes, null)
})

test('today cards use South African dates at the UTC boundary', () => {
  assert.equal(attendanceDay('2026-11-01T22:15:00Z'), '2026-11-02')
  const row = { ...inside, id: 4, action: 'sign_in', created_at: '2026-11-01T22:15:00Z' }
  const session = { session_id: 'midnight', user_id: 11, sign_in_event_id: 4, sign_in_at: row.created_at, sign_out_at: null, status: 'open' }
  const model = buildAttendanceHistory([row], [session], now)
  assert.equal(metric(model, 'today-sessions').count, 1)
  assert.equal(metric(model, 'latest-status').value, 'Signed in')
  assert.deepEqual(metric(model, 'latest-status').rows.map(item => item.id), [4])
})
