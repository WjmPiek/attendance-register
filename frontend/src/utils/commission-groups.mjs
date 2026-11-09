export function commissionGroups(rows,includeClosed=false) {
  const groups=new Map()
  for(const row of rows) {
    const active=['pending','approved'].includes(row.status)
    if(!active&&!includeClosed)continue
    const key=JSON.stringify([row.earning_branch_id ?? row.branch_name ?? '',row.commission_type])
    if(!groups.has(key))groups.set(key,{key,branch:row.branch_name || row.service_branch || 'Unassigned branch',category:row.commission_type,rows:[],approved:0,pending:0,approvedCount:0,pendingCount:0,unknown:false})
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
