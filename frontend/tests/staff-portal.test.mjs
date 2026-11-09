import test from 'node:test'
import assert from 'node:assert/strict'
import { usesStaffPortal,commissionTotals,commissionBranchTotals,commissionFiles,ownLeave,calendarDays,staffRoute,unreadStaffNotifications } from '../src/utils/staff-portal.mjs'

test('employees and managers share the simple portal while holder/admin roles retain management pages',()=>{
  for(const role of ['EmployeeUser','ManagerUser'])assert.equal(usesStaffPortal({roles:[role]}),true)
  for(const roles of [['FranchiseUser'],['SuperUser'],['FranchiseUser','ManagerUser'],['SuperUser','EmployeeUser']])assert.equal(usesStaffPortal({roles}),false)
})
test('two commission totals count verified approved amounts and keep queued or incomplete amounts waiting',()=>{
  const rows=[{employee_user_id:11,status:'approved',payment_eligible:true,calculated_amount:'100'},
    {employee_user_id:11,status:'pending',payment_eligible:true,expected_amount:'50'},
    {employee_user_id:11,status:'approved',payment_eligible:false,calculated_amount:'25'},
    {employee_user_id:11,status:'rejected',payment_eligible:true,calculated_amount:'999'},
    {employee_user_id:12,status:'approved',payment_eligible:true,calculated_amount:'999'}]
  assert.deepEqual(commissionTotals(rows,11),{approved:100,waiting:75,unknown:false})
})

test('branch totals reconcile to the combined totals and do not expose other staff',()=>{
  const rows=[{employee_user_id:11,earning_branch_id:9,branch_name:'Benoni',status:'approved',payment_eligible:true,calculated_amount:'100'},
    {employee_user_id:11,earning_branch_id:9,branch_name:'Benoni',status:'pending',payment_eligible:true,expected_amount:'50'},
    {employee_user_id:11,earning_branch_id:10,branch_name:'Daveyton',status:'pending',expected_amount:'75'},
    {employee_user_id:11,earning_branch_id:10,branch_name:'Daveyton',status:'pending',expected_amount:'0',estimate_available:false},
    {employee_user_id:12,earning_branch_id:10,branch_name:'Daveyton',status:'approved',payment_eligible:true,calculated_amount:'999'}]
  const branches=commissionBranchTotals(rows,11),all=commissionTotals(rows,11)
  assert.deepEqual(branches.map(row=>[row.branchName,row.approved,row.waiting,row.unknown]),[['Benoni',100,50,false],['Daveyton',0,75,true]])
  assert.equal(branches.reduce((sum,row)=>sum+row.approved,0),all.approved)
  assert.equal(branches.reduce((sum,row)=>sum+row.waiting,0),all.waiting)
})
test('branch file drilldowns normalise MF numbers and keep statuses, branches and staff separate',()=>{
  const base={employee_user_id:11,earning_branch_id:4,branch_name:'Northcliff',commission_type:'grave_service',calculated_amount:'75'}
  const rows=[{...base,id:1,reference:'MF 111137',status:'pending',expected_amount:'80'},
    {...base,id:2,reference:'111137 / Invoice 466 / Receipt 668',status:'pending',commission_type:'invoice_commission',expected_amount:'0',estimate_available:false},
    {...base,id:3,reference:'mf-111137',status:'approved',payment_eligible:true,calculated_amount:'100'},
    {...base,id:4,reference:'MF111137',status:'approved',payment_eligible:false,expected_amount:'20'},
    {...base,id:5,reference:'MF111137',earning_branch_id:11,branch_name:'Rivonia',status:'pending',expected_amount:'30'},
    {...base,id:6,reference:'MF111137',employee_user_id:12,status:'pending',expected_amount:'999'},
    {...base,id:7,reference:'MF111137',status:'rejected',expected_amount:'999'},
    {...base,id:8,reference:'MF111105',status:'cancelled',expected_amount:'999'}]
  const branches=commissionBranchTotals(rows,11),north=branches.find(branch=>branch.branchId===4),rivonia=branches.find(branch=>branch.branchId===11)
  assert.equal(north.files.waiting.length,1)
  assert.equal(north.files.waiting[0].reference,'MF111137')
  assert.deepEqual(north.files.waiting[0].items.map(item=>item.id),[1,2,4])
  assert.equal(north.files.waiting[0].unknown,true)
  assert.equal(north.files.waiting[0].total,north.waiting)
  assert.equal(north.files.approved[0].total,north.approved)
  assert.deepEqual(north.files.approved[0].items.map(item=>item.id),[3])
  assert.equal(rivonia.files.waiting[0].total,30)
  assert.deepEqual(commissionFiles([],11),{approved:[],waiting:[]})
})

test('own leave excludes a manager’s team and the calendar never treats rejected dates as authorised leave',()=>{
  const leave=[{applicant_user_id:11,status:'approved',start_date:'2026-11-02',end_date:'2026-11-06',return_date:'2026-11-09'},
    {applicant_user_id:11,status:'declined',start_date:'2026-11-16',end_date:'2026-11-17'},
    {applicant_user_id:12,status:'approved',start_date:'2026-11-10',end_date:'2026-11-11'}]
  const days=calendarDays('2026-11',ownLeave(leave,11)).filter(Boolean)
  assert.equal(days.find(day=>day.day===2).state,'leave')
  assert.equal(days.find(day=>day.day===9).state,'return')
  for(const day of [10,11,16,17])assert.equal(days.find(item=>item.day===day).state,'')
})
test('leave calendar handles month boundaries and leap years without marking a leave day as a return day',()=>{
  const items=[{status:'approved',start_date:'2028-02-28',end_date:'2028-03-01',return_date:'2028-03-02'},
    {status:'approved',start_date:'2028-03-02',end_date:'2028-03-03',return_date:'2028-03-06'}]
  assert.equal(calendarDays('2028-02',items).filter(Boolean).length,29)
  assert.equal(calendarDays('2028-03',items).find(day=>day?.day===2).state,'leave')
})
test('home is the normal landing page and existing attendance QR/notification links still reach a page',()=>{
  assert.equal(staffRoute(''),'home')
  assert.equal(staffRoute('?staff_page=leave-apply'),'leave-apply')
  assert.equal(staffRoute('?tab=commission'),'commissions')
  assert.equal(staffRoute('?staff_portal_page=team&staff_page=view'),'team')
  assert.equal(staffRoute('?staff_portal_page=team-commissions&commission_employee=12'),'team-commissions')
  assert.equal(staffRoute('?office_qr=example'),'attendance')
  assert.equal(staffRoute('?staff_page=business'),'home')
})


test('staff popups show unread personal updates once, oldest first, without leaking another recipient',()=>{
  const items=[{id:3,recipient_user_id:11,subject:'Leave approved',created_at:'2026-11-07T11:00:00'},
    {id:2,user_id:11,subject:'Claim finalised',created_at:'2026-11-07T10:00:00'},
    {id:2,user_id:11,subject:'Duplicate'},
    {id:4,recipient_user_id:12,user_id:11,subject:'Another recipient'},
    {id:5,user_id:11,is_read:true},{id:6,user_id:11,status:'read'},
    {id:7,recipient_user_id:null,user_id:null}]
  assert.deepEqual(unreadStaffNotifications(items,11).map(item=>item.id),[2,3])
  assert.deepEqual(unreadStaffNotifications(items,11,new Set(['2'])).map(item=>item.id),[3])
  assert.deepEqual(unreadStaffNotifications(null,11),[])
  assert.equal(staffRoute('?staff_portal_page=notifications'),'home')
})
