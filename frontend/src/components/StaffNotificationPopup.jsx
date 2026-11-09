import { useEffect, useRef, useState } from 'react'
import { getNotifications, markNotificationRead } from '../api/client'
import { unreadStaffNotifications } from '../utils/staff-portal.mjs'
import StaffPopup from './StaffPopup'

export default function StaffNotificationPopup({me, paused=false}) {
  const [items,setItems]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const [reminderBusy,setReminderBusy]=useState(false),[reminderError,setReminderError]=useState('')
  const dismissed=useRef(new Set()),closing=useRef(false)
  const dismissingReminders=useRef(false)
  useEffect(()=>{
    let active=true
    const poll=async()=>{
      try {
        const data=await getNotifications()
        if(active)setItems(unreadStaffNotifications(data,me.id,dismissed.current))
      } catch { /* Retry on the next poll without interrupting a request form. */ }
    }
    poll();const timer=window.setInterval(poll,10000)
    return()=>{active=false;window.clearInterval(timer)}
  },[me.id])
  const reminders=items.filter(item=>item.subject==='Document uploads required')
  const notification=items.find(item=>item.subject!=='Document uploads required')
  const dismissReminders=async()=>{
    if(dismissingReminders.current)return
    dismissingReminders.current=true;setReminderBusy(true);setReminderError('')
    try {
      const results=await Promise.allSettled(reminders.map(async item=>{
        await markNotificationRead(item.id)
        dismissed.current.add(String(item.id))
      }))
      setItems(current=>unreadStaffNotifications(current,me.id,dismissed.current))
      if(results.some(result=>result.status==='rejected'))setReminderError('Some reminders could not be dismissed. You can continue and try again later.')
    } finally {dismissingReminders.current=false;setReminderBusy(false)}
  }
  const close=async()=>{
    if(closing.current||!notification)return
    closing.current=true;setBusy(true);setError('')
    try {
      await markNotificationRead(notification.id)
      dismissed.current.add(String(notification.id))
      setItems(current=>unreadStaffNotifications(current,me.id,dismissed.current))
    } catch {setError('Could not save your acknowledgement. Please press OK again.')}
    finally {closing.current=false;setBusy(false)}
  }
  if(paused)return null
  return <>
    {reminders.length>0&&<aside className="staff-document-reminder" aria-label="Commission document reminders">
      <p role="status"><strong>Waiting to be finalised</strong> · {reminders.length} commission document reminder{reminders.length===1?'':'s'}. Document uploads are required before approval. You can continue using the system and submit other claims.</p>
      <details><summary>View document reminders</summary><ul>{[...new Set(reminders.map(item=>item.message))].map(message=><li key={message}>{message}</li>)}</ul></details>
      {reminderError&&<p role="alert">{reminderError}</p>}
      <button type="button" disabled={reminderBusy} onClick={dismissReminders}>{reminderBusy?'Dismissing…':'Dismiss document reminders'}</button>
    </aside>}
    {notification&&<StaffPopup key={notification.id} title={notification.subject||'Task update'} message={notification.message} onClose={close} busy={busy} error={error}/>}
  </>
}
