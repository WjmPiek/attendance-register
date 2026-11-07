import test from 'node:test'
import assert from 'node:assert/strict'
import { usesStaffPortal,commissionTotals,ownLeave,calendarDays,staffRoute } from '../src/utils/staff-portal.mjs'

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
