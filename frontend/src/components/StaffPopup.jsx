import { useEffect, useRef } from 'react'

export default function StaffPopup({title, message, onClose, busy=false, error=''}) {
  const button=useRef(null)
  useEffect(()=>{
    const previous=document.activeElement
    button.current?.focus()
    return()=>{if(previous?.isConnected)previous.focus()}
  },[])
  return <div className="staff-popup-backdrop"><section role="alertdialog" aria-modal="true" aria-labelledby="staff-popup-title" aria-describedby={message?'staff-popup-message':undefined} className="staff-popup" onKeyDown={event=>{
    if(event.key==='Escape'&&!busy)onClose()
    if(event.key==='Tab'){event.preventDefault();button.current?.focus()}
  }}><h2 id="staff-popup-title">{title}</h2>{message&&<p id="staff-popup-message">{message}</p>}{error&&<p role="alert" className="error-message">{error}</p>}<button ref={button} type="button" aria-disabled={busy} onClick={()=>{if(!busy)onClose()}}>{busy?'Saving…':'OK'}</button></section></div>
}
