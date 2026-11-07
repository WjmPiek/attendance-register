import { useEffect, useRef, useState } from 'react'
import { apiRequest, getCommissionEntries, getNotifications, markNotificationRead } from '../api/client'
import { staffRoute, commissionTotals } from '../utils/staff-portal.mjs'
import { useCommissionMonth } from '../utils/useCommissionMonth'
import { notifyAttendanceParent } from '../embeddedAttendance'
import ServiceClaimPanel from '../components/ServiceClaimPanel'
import StaffLeave from '../components/StaffLeave'
import StaffDocuments from '../components/StaffDocuments'
import AttendanceExceptionPopup from '../components/AttendanceExceptionPopup'
import MobileAttendancePage from './MobileAttendancePage'
import AttendanceHistoryPage from './AttendanceHistoryPage'
import AttendanceApprovalPage from './AttendanceApprovalPage'
import FranchiseStaffPage from './FranchiseStaffPage'
import CommissionPage from './CommissionPage'
import UploadProofPage from './UploadProofPage'
import PayrollPage from './PayrollPage'
import Irp5DocumentsPage from './Irp5DocumentsPage'
import MyProfilePage from './MyProfilePage'
import DigitalIdCard from '../components/DigitalIdCard'
import './StaffPortal.css'

const titles={home:'Home',claim:'Claim',commissions:'Commissions',leave:'Leave Days','leave-apply':'Leave Application','leave-approved':'Leave Approved','leave-rejected':'Leave Rejected','leave-pending':'Pending Requests',payslips:'Payslips',irp5:'IRP5',notifications:'Notifications',more:'More',attendance:'Sign In / Out',history:'Attendance History','id-card':'My ID',profile:'My Profile',upload:'Upload Documents',team:'My Team','team-commissions':'Team Commissions',approvals:'Approvals','attendance-approvals':'Attendance Requests','leave-requests':'Leave Requests','manage-payslips':'Manage Payslips','manage-irp5':'Manage IRP5'}
const homeButtons=[['attendance','Sign In / Out'],['claim','Claim'],['commissions','Commissions'],['leave','Leave Days'],['payslips','Payslips'],['irp5','IRP5'],['notifications','Notifications'],['more','More']]
const money=value=>`R ${Number(value || 0).toLocaleString('en-ZA',{minimumFractionDigits:2,maximumFractionDigits:2})}`

function SubmissionPopup({onClose}) {
  const button=useRef(null)
  useEffect(()=>{button.current?.focus()},[])
  return <div className="staff-popup-backdrop"><section role="alertdialog" aria-modal="true" aria-labelledby="staff-request-sent" className="staff-popup" onKeyDown={event=>{if(event.key==='Escape')onClose();if(event.key==='Tab'){event.preventDefault();button.current?.focus()}}}><h2 id="staff-request-sent">Your request has been sent.</h2><button ref={button} type="button" onClick={onClose}>OK</button></section></div>
}

function StaffCommissionAmounts({me}) {
  const [month]=useCommissionMonth(),[totals,setTotals]=useState(null),[error,setError]=useState('')
  useEffect(()=>{
    let active=true
    const [year,number]=month.split('-').map(Number)
    const load=()=>getCommissionEntries({employeeUserId:me.id,fromDate:new Date(Date.UTC(year,number-2,26)).toISOString().slice(0,10),toDate:`${month}-25`})
      .then(data=>{if(active){setTotals(commissionTotals([...data.items,...(data.pending_imports||[])],me.id));setError('')}}).catch(e=>{if(active)setError(e.message)})
    setTotals(null);load();const timer=setInterval(load,20000)
    return()=>{active=false;clearInterval(timer)}
  },[month,me.id])
  return <section>{error&&<p role="alert" className="error-message">{error}</p>}{!totals&&!error&&<p role="status">Loading…</p>}{totals&&<><p className="staff-period">{new Date(`${month}-01T12:00:00Z`).toLocaleDateString('en-ZA',{month:'long',year:'numeric'})}</p><div className="staff-amounts"><section className="approved"><h2>Approved</h2><strong>{money(totals.approved)}</strong></section><section className="waiting"><h2>Waiting to be finalised</h2><strong>{totals.unknown&&totals.waiting===0?'Awaiting calculation':money(totals.waiting)}</strong>{totals.unknown&&totals.waiting>0&&<small>More amounts await documents.</small>}</section></div></>}</section>
}

function StaffNotifications({me,navigate}) {
  const [items,setItems]=useState(null),[error,setError]=useState('')
  useEffect(()=>{let active=true;const load=()=>getNotifications().then(data=>{if(active)setItems((Array.isArray(data)?data:[]).filter(item=>Number(item.recipient_user_id??item.user_id)===Number(me.id)))}).catch(e=>{if(active)setError(e.message)});load();const timer=setInterval(load,20000);return()=>{active=false;clearInterval(timer)}},[me.id])
  const open=async item=>{setError('');try{await markNotificationRead(item.id);navigate(item.target_tab==='leave'?'leave':item.target_tab==='commission'?'commissions':item.target_tab==='approvals'?'attendance-approvals':'home')}catch(e){setError(e.message)}}
  return <section>{error&&<p role="alert" className="error-message">{error}</p>}{!items&&!error&&<p role="status">Loading…</p>}<div className="staff-notification-list">{items?.map(item=><button type="button" key={item.id} onClick={()=>open(item)}><strong>{item.subject}</strong><span>{item.message}</span></button>)}</div>{items?.length===0&&<p>No notifications.</p>}</section>
}

export default function StaffPortal({me,onLogout,embedded=false}) {
  const [page,setPage]=useState(()=>staffRoute(window.location.search)),[sent,setSent]=useState(false)
  const [canImport,setCanImport]=useState(null)
  const manager=me.roles.includes('ManagerUser'),finance=(me.employee_role||'').toLowerCase().includes('finance')
  useEffect(()=>{let active=true;apiRequest('/receipt-commissions/access').then(result=>{if(active)setCanImport(Boolean(result.can_import))}).catch(()=>{if(active)setCanImport(false)});return()=>{active=false}},[me.id])
  useEffect(()=>{const sync=()=>setPage(staffRoute(window.location.search));window.addEventListener('popstate',sync);return()=>window.removeEventListener('popstate',sync)},[])
  const navigate=(next,{replace=false,preserveEmployee=false}={})=>{
    const url=new URL(window.location.href)
    url.searchParams.set('staff_portal_page',next);url.searchParams.delete('staff_page');url.searchParams.delete('tab')
    for(const key of ['staff_subtab','staff_action'])url.searchParams.delete(key)
    if(!preserveEmployee)url.searchParams.delete('commission_employee')
    window.history[replace?'replaceState':'pushState']({},'',url)
    setPage(next);window.scrollTo(0,0)
    if(embedded)notifyAttendanceParent('martins:attendance-scroll-top')
  }
  const submitted=()=>{navigate('home',{replace:true});setSent(true)}
  const restricted=(['team','team-commissions','approvals','attendance-approvals','leave-requests'].includes(page)&&!manager)||(['manage-payslips','manage-irp5'].includes(page)&&!finance)||(page==='upload'&&canImport===false)
  const current=restricted?'home':page
  const tools=[['history','Attendance History'],['id-card','My ID'],['profile','My Profile'],...(canImport?[['upload','Upload Documents']]:[]),...(manager?[['approvals','Approvals'],['team','My Team']]:[]),...(finance?[['manage-payslips','Manage Payslips'],['manage-irp5','Manage IRP5']]:[])]
  return <div className={`staff-portal${embedded?' staff-portal-embedded':''}`}>
    <header className="staff-portal-header">{current!=='home'&&<button type="button" onClick={()=>navigate('home',{replace:true})}>Home</button>}<span>{me.full_name || me.username || me.email}</span><button type="button" onClick={onLogout}>Logout</button></header>
    <main className="staff-portal-main" key={current}>
      <h1>{titles[current]||'Home'}</h1>
      {current==='home'&&<nav className="staff-button-grid" aria-label="Home">{homeButtons.map(([id,label])=><button type="button" key={id} onClick={()=>navigate(id)}>{label}</button>)}</nav>}
      {current==='claim'&&<ServiceClaimPanel me={me} simple onSaved={submitted}/>}
      {current==='commissions'&&<StaffCommissionAmounts me={me}/>}
      {(current==='leave'||current.startsWith('leave-'))&&<StaffLeave me={me} page={current} navigate={navigate} onSubmitted={submitted}/>}
      {['payslips','irp5'].includes(current)&&<StaffDocuments kind={current}/>}
      {current==='notifications'&&<StaffNotifications me={me} navigate={navigate}/>}
      {current==='more'&&<nav className="staff-button-grid" aria-label="More">{tools.map(([id,label])=><button type="button" key={id} onClick={()=>navigate(id)}>{label}</button>)}</nav>}
      {current==='attendance'&&<MobileAttendancePage me={me} onDone={()=>navigate('home',{replace:true})}/>}
      {current==='history'&&<AttendanceHistoryPage me={me}/>}
      {current==='id-card'&&<DigitalIdCard/>}
      {current==='profile'&&<MyProfilePage me={me} detailsOnly/>}
      {current==='upload'&&(canImport===null?<p role="status">Loading…</p>:canImport&&<UploadProofPage/>)}
      {current==='team'&&manager&&<FranchiseStaffPage me={me} onNavigate={target=>navigate(target==='commission'?'team-commissions':'home',{preserveEmployee:target==='commission'})}/>}
      {current==='team-commissions'&&manager&&<CommissionPage me={me}/>}
      {current==='approvals'&&manager&&<nav className="staff-button-grid" aria-label="Approvals"><button onClick={()=>navigate('attendance-approvals')}>Attendance Requests</button><button onClick={()=>navigate('leave-requests')}>Leave Requests</button></nav>}
      {current==='attendance-approvals'&&manager&&<AttendanceApprovalPage me={me}/>}
      {current==='manage-payslips'&&finance&&<PayrollPage me={me}/>}
      {current==='manage-irp5'&&finance&&<Irp5DocumentsPage me={me}/>}
    </main>
    {sent&&<SubmissionPopup onClose={()=>setSent(false)}/>}
    {manager&&<AttendanceExceptionPopup me={me} onNavigate={()=>navigate('attendance-approvals')}/>}
  </div>
}
