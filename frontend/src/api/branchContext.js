import {getSessionValue,setSessionValue,removeSessionValue} from './sessionContext.js'
const KEY = 'attendance.staff-branch'
export function getStaffBranchId() { return getSessionValue(KEY) || '' }
export function setStaffBranchId(value) { if (value) setSessionValue(KEY,value); else removeSessionValue(KEY) }
