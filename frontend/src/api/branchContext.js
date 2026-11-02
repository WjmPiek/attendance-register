const KEY = 'attendance.staff-branch'
export function getStaffBranchId() { try { return sessionStorage.getItem(KEY) || '' } catch { return '' } }
export function setStaffBranchId(value) { try { if (value) sessionStorage.setItem(KEY,String(value)); else sessionStorage.removeItem(KEY) } catch {} }
