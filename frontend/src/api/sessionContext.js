// Preserve page context when a browser blocks storage in an integrated module.
const memory = new Map()
const blockedKeys = new Set()
export function getSessionValue(key) {
  if (blockedKeys.has(key)) return memory.get(key) || null
  try { return sessionStorage.getItem(key) }
  catch { return memory.get(key) || null }
}
export function setSessionValue(key, value) {
  memory.set(key, String(value))
  try { sessionStorage.setItem(key, String(value)); blockedKeys.delete(key) }
  catch { blockedKeys.add(key) }
}
export function removeSessionValue(key) {
  memory.delete(key)
  try { sessionStorage.removeItem(key) }
  catch {}
}
