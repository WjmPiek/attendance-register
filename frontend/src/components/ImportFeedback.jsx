import { useEffect, useId, useRef, useState } from 'react'
import { notifyAttendanceParent } from '../embeddedAttendance'

export function scrollImportTop() {
  window.scrollTo({top:0,behavior:'auto'})
  notifyAttendanceParent('martins:attendance-scroll-top')
}

export function detectedImportBranch(result, previous='') {
  if(!result?.records?.length) return previous
  const ids=[...new Set(result.records.map(r=>r.external_branch_id?`external:${r.external_branch_id}`:r.earning_branch_id?`linked:${r.earning_branch_id}`:'').filter(Boolean))]
  return ids.length===1?ids[0]:''
}

export default function ImportFeedback({error,warnings=[],notice}) {
  const [message,setMessage]=useState('')
  const button=useRef(null),previousFocus=useRef(null),title=useId()
  const warningText=warnings.map(w=>typeof w==='string'?w:`${w.filename||'Document'}${w.page?` · page ${w.page}`:''}: ${w.error}`).join('\n')
  useEffect(()=>{const value=error||warningText;if(value){previousFocus.current=document.activeElement;scrollImportTop();setMessage(value)}},[error,warningText])
  useEffect(()=>{if(message)button.current?.focus({preventScroll:true})},[message])
  useEffect(()=>{if(notice)scrollImportTop()},[notice])
  const close=()=>{setMessage('');previousFocus.current?.focus?.({preventScroll:true})}
  if(!message)return null
  return <div className="import-message-backdrop"><section className="import-message-popup" role="alertdialog" aria-modal="true" aria-labelledby={title} onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();close()}if(e.key==='Tab'){e.preventDefault();button.current?.focus()}}}>
    <h2 id={title}>Document upload needs attention</h2><p>{message}</p><button ref={button} type="button" onClick={close}>Close message</button>
  </section></div>
}
