import { useEffect, useState } from 'react'
import { apiRequest, applyLeave, approveLeaveApplication, declineLeaveApplication } from '../api/client'
import { ownLeave, calendarDays } from '../utils/staff-portal.mjs'

const leaveTypes=['Annual Leave','Sick Leave','Family Responsibility Leave','Unpaid Leave','Study Leave']
const today=()=>new Date(Date.now()+7200000).toISOString().slice(0,10)
const formatDate=date=>date?new Date(`${date}T12:00:00Z`).toLocaleDateString('en-ZA',{day:'numeric',month:'short',year:'numeric'}):'Not set'
export default function StaffLeave({ me, page, navigate, onSubmitted }) {
  const [items,setItems]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false)
  const [month,setMonth]=useState(()=>today().slice(0,7))
  const [form,setForm]=useState({leave_type:'Annual Leave',start_date:'',end_date:'',reason:''})
  useEffect(()=>{
    if(page==='leave-apply')return
    let active=true;setItems(null);setError('')
    const refresh=()=>apiRequest(`/leave/applications?own_only=${page==='leave-requests'?'false':'true'}&include_past=${page==='leave-requests'?'false':'true'}`)
      .then(data=>{if(active)setItems(page==='leave-requests'?data.filter(item=>Number(item.applicant_user_id)!==Number(me.id)&&item.status==='pending'):ownLeave(data,me.id))})
      .catch(e=>{if(active)setError(e.message)})
    refresh();const timer=setInterval(refresh,20000)
    return()=>{active=false;clearInterval(timer)}
  },[page,me.id])
  const submit=async event=>{
    event.preventDefault();setError('')
    if(form.end_date<form.start_date){setError('End date must be on or after the start date.');return}
    setBusy(true)
    try {await applyLeave(form);onSubmitted()}catch(e){setError(e.message)}finally{setBusy(false)}
  }
  const decide=async (id,approved)=>{
    const note=window.prompt(approved?'Approval note (optional)':'Reason for rejection')
    if(note===null)return
    setBusy(true);setError('')
    try {await (approved?approveLeaveApplication:declineLeaveApplication)(id,note);onSubmitted()}catch(e){setError(e.message)}finally{setBusy(false)}
  }
  if(page==='leave-apply')return <form className="staff-simple-form" onSubmit={submit}>{error&&<p role="alert" className="error-message">{error}</p>}
    <label>Leave type<select disabled={busy} value={form.leave_type} onChange={e=>setForm({...form,leave_type:e.target.value})}>{leaveTypes.map(type=><option key={type}>{type}</option>)}</select></label>
    <label>From<input required type="date" disabled={busy} value={form.start_date} onChange={e=>setForm({...form,start_date:e.target.value})}/></label>
    <label>To<input required type="date" disabled={busy} min={form.start_date} value={form.end_date} onChange={e=>setForm({...form,end_date:e.target.value})}/></label>
    <label>Reason<textarea disabled={busy} value={form.reason} onChange={e=>setForm({...form,reason:e.target.value})}/></label>
    <button disabled={busy}>{busy?'Submitting…':'Submit'}</button>
  </form>
  const selected=items?.filter(item=>page==='leave-approved'?item.status==='approved':page==='leave-rejected'?['declined','rejected'].includes(item.status):page==='leave-pending'?item.status==='pending':true)
  const move=step=>{const [year,number]=month.split('-').map(Number);setMonth(new Date(Date.UTC(year,number-1+step,1)).toISOString().slice(0,7))}
  return <section>{error&&<p role="alert" className="error-message">{error}</p>}
    {page==='leave'?<>
      <nav className="staff-button-grid" aria-label="Leave days"><button onClick={()=>navigate('leave-apply')}>Leave Application</button><button onClick={()=>navigate('leave-approved')}>Leave Approved</button><button onClick={()=>navigate('leave-rejected')}>Leave Rejected</button><button onClick={()=>navigate('leave-pending')}>Pending Requests</button></nav>
      {items&&<section className="staff-leave-calendar"><div className="staff-calendar-heading"><button type="button" onClick={()=>move(-1)} aria-label="Previous month">‹</button><label><span className="sr-only">Calendar month</span><input aria-label="Calendar month" type="month" value={month} onChange={e=>{if(e.target.value)setMonth(e.target.value)}}/></label><button type="button" onClick={()=>move(1)} aria-label="Next month">›</button></div>
        <div className="staff-calendar-grid">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(day=><span className="staff-calendar-weekday" key={day}>{day}</span>)}{calendarDays(month,items).map((cell,index)=>cell?<span key={cell.date} className={`staff-calendar-day ${cell.state}`} aria-label={`${cell.date}${cell.state==='leave'?' On leave':cell.state==='return'?' Back at work':''}`}>{cell.day}</span>:<span key={`empty-${index}`}/>)}</div>
        <div className="staff-calendar-legend"><span className="leave">On leave</span><span className="return">Back at work</span></div>
      </section>}
    </>:<div className="staff-record-list">{selected?.map(item=><article key={item.id}>{page==='leave-requests'&&<strong>{item.full_name || `${item.name} ${item.surname}`}</strong>}<h2>{item.leave_type}</h2><p>{formatDate(item.start_date)} – {formatDate(item.end_date)}</p>{item.status==='approved'&&<p className="staff-return-date">Back at work: {formatDate(item.return_date)}</p>}{item.decision_note&&<p>{item.decision_note}</p>}{page==='leave-requests'&&<><p>{item.reason}</p><div className="staff-button-grid"><button disabled={busy} onClick={()=>decide(item.id,true)}>Approve</button><button disabled={busy} onClick={()=>decide(item.id,false)}>Reject</button></div></>}</article>)}{selected?.length===0&&<p>No requests.</p>}</div>}
    {!items&&!error&&<p role="status">Loading…</p>}
  </section>
}
