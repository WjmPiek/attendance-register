const TOKEN_KEY = 'token'
export const AUTH_INVALID_EVENT = 'attendance:auth-invalid'

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function clearAccessToken(reason = 'Your session has expired. Please sign in again.') {
  localStorage.removeItem(TOKEN_KEY)
  window.dispatchEvent(new CustomEvent(AUTH_INVALID_EVENT, { detail: { reason } }))
}
