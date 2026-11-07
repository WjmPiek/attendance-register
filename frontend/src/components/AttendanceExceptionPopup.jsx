import { useEffect, useState } from 'react'
import { getNotifications, markNotificationRead } from '../api/client'
import { formatJohannesburgDateTime } from '../utils/dateTime'

export default function AttendanceExceptionPopup({ me, onNavigate }) {
  const canReceive = me.roles.includes('FranchiseUser') || me.roles.includes('ManagerUser')
  const [notification, setNotification] = useState(null)

  useEffect(() => {
    if (!canReceive) return undefined
    let active = true
    const poll = async () => {
      try {
        const items = await getNotifications()
        if (!active) return
        const next = (Array.isArray(items) ? items : []).find((item) => (
          item.notification_type === 'attendance_outside_area'
          && !item.is_read
          && Number(item.recipient_user_id) === Number(me.id)
        ))
        setNotification((current) => current?.id === next?.id ? current : (next || null))
      } catch {
        // Normal page error handling remains available; popup polling is non-blocking.
      }
    }
    poll()
    const timer = window.setInterval(poll, 10000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [canReceive, me.id])

  if (!notification) return null

  const close = async (openTarget = false) => {
    try {
      await markNotificationRead(notification.id)
    } catch {
      // The popup can still close if the read receipt cannot be saved.
    }
    const target = notification.related_table === 'attendance_events' ? 'approvals' : notification.target_tab
    setNotification(null)
    if (openTarget && target) onNavigate(target)
  }

  return (
    <div className="attendance-alert-backdrop" role="alertdialog" aria-modal="true" aria-labelledby="attendance-alert-title">
      <section className="attendance-alert-popup">
        <p className="eyebrow">GPS attendance warning</p>
        <h2 id="attendance-alert-title">{notification.subject}</h2>
        <p>{notification.message}</p>
        <small>{formatJohannesburgDateTime(notification.created_at)}</small>
        <div className="button-row">
          <button type="button" className="danger-button" onClick={() => close(true)}>Open attendance record</button>
          <button type="button" className="glass-button" onClick={() => close(false)}>Dismiss</button>
        </div>
      </section>
    </div>
  )
}

