export const staffWeekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
export const defaultStaffWeek = () => staffWeekdays.map((_, index) => index === 6 ? null : { start: '08:00', end: index === 5 ? '13:00' : '17:00' })

export function staffWorkWeek(staff) {
  let week = staff.work_week
  if (typeof week === 'string') { try { week = JSON.parse(week) } catch { week = null } }
  if (Array.isArray(week) && week.length === 7) return week
  return staffWeekdays.map(() => ({ start: staff.work_start_time || '08:00', end: staff.work_end_time || '17:00' }))
}

export function StaffHoursSummary({ staff }) {
  return <details><summary>Weekly hours</summary><ul>{staffWorkWeek(staff).map((day, index) => <li key={staffWeekdays[index]}>{staffWeekdays[index]}: {day ? `${day.start}–${day.end}` : 'Not working'}</li>)}</ul></details>
}

export default function StaffWorkingHours({ value, onChange }) {
  const update = (index, day) => onChange(value.map((current, position) => position === index ? day : current))
  return <fieldset className="staff-weekly-hours"><legend>Business hours</legend><p className="muted">Set each day separately. These hours are also used to classify removal commissions. Untick days the staff member does not normally work.</p>{staffWeekdays.map((name, index) => <div className="staff-working-day" key={name}>
    <label className="staff-working-day-toggle"><input type="checkbox" checked={value[index] !== null} onChange={e => update(index, e.target.checked ? { start: '08:00', end: index === 5 ? '13:00' : '17:00' } : null)}/>{name}</label>
    <label>Start<input aria-label={`${name} start`} type="time" required disabled={!value[index]} value={value[index]?.start || ''} onChange={e => update(index, { ...value[index], start: e.target.value })}/></label>
    <label>End<input aria-label={`${name} end`} type="time" required disabled={!value[index]} value={value[index]?.end || ''} onChange={e => update(index, { ...value[index], end: e.target.value })}/></label>
  </div>)}</fieldset>
}
