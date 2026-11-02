import {setStaffBranchId} from './branchContext.js'
import {embeddedParentOrigin} from '../embeddedAttendance.js'
const TOKEN_KEY = 'token'
export const AUTH_INVALID_EVENT = 'attendance:auth-invalid'
let memoryToken = null
let memoryOnly = false

export function getAccessToken() {
  if (memoryOnly || embeddedParentOrigin()) return memoryToken
  try { return localStorage.getItem(TOKEN_KEY) }
  catch { return memoryToken }
}

export function setAccessToken(token) {
  if (token !== getAccessToken()) setStaffBranchId('')
  memoryToken = token || null
  // A host-page session belongs only to this frame and its selected branch.
  if (embeddedParentOrigin()) { memoryOnly = true; return }
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
    memoryOnly = false
  } catch {
    // Some browsers block persistent storage in an integrated module.
    // The signed launch can still establish a session for this page.
    memoryOnly = true
  }
}

export function clearAccessToken(reason = 'Your session has expired. Please sign in again.') {
  setAccessToken(null)
  setStaffBranchId('')
  window.dispatchEvent(new CustomEvent(AUTH_INVALID_EVENT, { detail: { reason } }))
}
