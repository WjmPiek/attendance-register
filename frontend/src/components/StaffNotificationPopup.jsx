import { useEffect, useRef, useState } from 'react'
import { getNotifications, markNotificationRead } from '../api/client'
import { unreadStaffNotifications } from '../utils/staff-portal.mjs'
import StaffPopup from './StaffPopup'

export default function StaffNotificationPopup({me, paused=false}) {
  const [items,setItems]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const dismissed=useRef(new Set()),closing=useRef(false)
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
  const notification=items[0]
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
  if(paused||!notification)return null
  return <StaffPopup key={notification.id} title={notification.subject||'Task update'} message={notification.message} onClose={close} busy={busy} error={error}/>
}
