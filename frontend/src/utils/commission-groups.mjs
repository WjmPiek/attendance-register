export function commissionGroups(rows,includeClosed=false) {
  const groups=new Map()
  for(const row of rows) {
    const active=['pending','approved'].includes(row.status)
    if(!active&&!includeClosed)continue
    const key=JSON.stringify([row.earning_branch_id ?? row.branch_name ?? '',row.commission_type])
    if(!groups.has(key))groups.set(key,{key,branchKey:String(row.earning_branch_id ?? row.branch_name ?? ''),branch:row.branch_name || row.service_branch || 'Unassigned branch',category:row.commission_type,rows:[],approved:0,pending:0,approvedCount:0,pendingCount:0,unknown:false})
    const group=groups.get(key)
    group.rows.push(row)
    if(!active)continue
    const approved=row.status==='approved'&&row.payment_eligible
    const value=Number(approved?row.calculated_amount:row.expected_amount ?? row.calculated_amount ?? 0)
    group[approved?'approved':'pending']+=Number.isFinite(value)?value:0
    group[approved?'approvedCount':'pendingCount']+=1
    if(!approved&&row.estimate_available===false)group.unknown=true
  }
  return [...groups.values()].sort((a,b)=>a.branch.localeCompare(b.branch)||a.category.localeCompare(b.category))
}

export function commissionBranches(groups) {
  const branches=new Map()
  for(const group of groups) {
    if(!branches.has(group.branchKey))branches.set(group.branchKey,{key:group.branchKey,name:group.branch,groups:[]})
    branches.get(group.branchKey).groups.push(group)
  }
  return [...branches.values()]
}

export function readCommissionView(search,personId) {
  const params=new URLSearchParams(search)
  if(params.get('commission_view_person')!==String(personId))return {key:'',month:'',mf:''}
  const month=params.get('commission_view_month') || ''
  return {key:params.get('commission_view_group') || '',month:/^\d{4}-(0[1-9]|1[0-2])$/.test(month)?month:'',mf:commissionMfKey(params.get('commission_view_mf'))}
}

export function commissionMfKey(reference) {
  return String(reference || '').split(/ \/ (?:Invoice|Receipt) /i)[0].trim().replace(/^MF[\s-]*/i,'').toUpperCase().replace(/[^A-Z0-9]/g,'')
}

export function commissionMfFiles(rows) {
  const files=new Map()
  for(const row of rows) {
    const key=commissionMfKey(row.reference)
    if(!key)continue
    if(!files.has(key))files.set(key,{key,reference:`MF${key}`,rows:[]})
    files.get(key).rows.push(row)
  }
  return [...files.values()].sort((a,b)=>a.key.localeCompare(b.key,undefined,{numeric:true}))
}
