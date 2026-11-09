export function usesStaffPortal(me) {
  const roles=me?.roles || []
  return !roles.some(role=>['SuperUser','FranchiseUser'].includes(role)) && roles.some(role=>['EmployeeUser','ManagerUser'].includes(role))
}

export function commissionTotals(rows, uid) {
  return rows.filter(row=>Number(row.employee_user_id)===Number(uid)).reduce((result,row)=>{
    if (!['pending','approved'].includes(row.status)) return result
    const approved=row.status==='approved' && row.payment_eligible
    const amount=Number(approved ? row.calculated_amount : row.expected_amount ?? row.calculated_amount ?? 0)
    result[approved?'approved':'waiting']+=Number.isFinite(amount)?amount:0
    if (!approved && row.estimate_available===false) result.unknown=true
    return result
  },{approved:0,waiting:0,unknown:false})
}

export function commissionFiles(rows, uid) {
  const groups={approved:new Map(),waiting:new Map()}
  for(const row of rows) {
    if(Number(row.employee_user_id)!==Number(uid) || !['pending','approved'].includes(row.status))continue
    const approved=row.status==='approved' && row.payment_eligible
    const reference=String(row.reference || '').split(/ \/ (?:Invoice|Receipt) /i)[0].trim()
      .replace(/^MF[\s-]*/i,'').toUpperCase().replace(/[^A-Z0-9]/g,'')
    const key=reference || `unreferenced:${row.id}`
    const files=groups[approved?'approved':'waiting']
    if(!files.has(key))files.set(key,{key,reference:reference?`MF${reference}`:'MF number unavailable',items:[],total:0,unknown:false})
    const file=files.get(key)
    const value=Number(approved?row.calculated_amount:row.expected_amount ?? row.calculated_amount ?? 0)
    const amount=Number.isFinite(value)?value:0
    const unknown=!approved && row.estimate_available===false
    file.items.push({id:row.id,category:row.commission_type,amount,unknown})
    file.total+=amount
    file.unknown ||= unknown
  }
  return Object.fromEntries(Object.entries(groups).map(([status,files])=>[status,[...files.values()].sort((a,b)=>a.reference.localeCompare(b.reference,undefined,{numeric:true}))]))
}

export function commissionBranchTotals(rows, uid) {
  const groups=new Map()
  for(const row of rows) {
    if(Number(row.employee_user_id)!==Number(uid) || !['pending','approved'].includes(row.status))continue
    const key=String(row.earning_branch_id ?? row.branch_name ?? 'unassigned')
    if(!groups.has(key))groups.set(key,{branchId:row.earning_branch_id,branchName:row.branch_name || row.service_branch || 'Unassigned branch',rows:[]})
    groups.get(key).rows.push(row)
  }
  return [...groups.values()].map(group=>({branchId:group.branchId,branchName:group.branchName,...commissionTotals(group.rows,uid),files:commissionFiles(group.rows,uid)}))
    .sort((a,b)=>a.branchName.localeCompare(b.branchName))
}

export function ownLeave(items,uid) {
  return items.filter(item=>Number(item.applicant_user_id)===Number(uid))
}

export function calendarDays(month,items) {
  const [year,number]=month.split('-').map(Number)
  const first=new Date(Date.UTC(year,number-1,1)),count=new Date(Date.UTC(year,number,0)).getUTCDate()
  const cells=Array.from({length:(first.getUTCDay()+6)%7},()=>null)
  const approved=items.filter(item=>item.status==='approved')
  for(let day=1;day<=count;day++) {
    const date=`${month}-${String(day).padStart(2,'0')}`
    const onLeave=approved.some(item=>item.start_date<=date && item.end_date>=date)
    const back=!onLeave && approved.some(item=>item.return_date===date)
    cells.push({day,date,state:onLeave?'leave':back?'return':''})
  }
  return cells
}

const pages=new Set(['home','claim','commissions','leave','leave-apply','leave-approved','leave-rejected','leave-pending','payslips','irp5','more','attendance','history','id-card','profile','upload','team','team-commissions','approvals','attendance-approvals','leave-requests','manage-payslips','manage-irp5'])
export function staffRoute(search) {
  const query=new URLSearchParams(search)
  if(query.has('office_qr'))return 'attendance'
  const explicit=query.get('staff_portal_page') || query.get('staff_page')
  if(pages.has(explicit))return explicit
  return {commission:'commissions',leave:'leave',payroll:'payslips',irp5:'irp5',attendance:'attendance',history:'history',profile:'profile','employee-card':'id-card',staff:'upload',approvals:'attendance-approvals'}[query.get('tab')] || 'home'
}


export function unreadStaffNotifications(items, uid, dismissed = new Set()) {
  const seen = new Set(dismissed)
  return (Array.isArray(items) ? items : []).filter(item => {
    const id = String(item.id ?? '')
    if (!id || seen.has(id) || item.is_read || item.status === 'read'
      || Number(item.recipient_user_id ?? item.user_id) !== Number(uid)) return false
    seen.add(id)
    return true
  }).sort((a, b) => String(a.created_at || '').localeCompare(String(b.created_at || '')) || Number(a.id) - Number(b.id))
}
