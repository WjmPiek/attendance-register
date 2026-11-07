// The open default finance cycle advances at the South African cutoff.
export function currentCommissionMonth(now = new Date()) {
  const local = new Date(now.getTime() + 2 * 60 * 60 * 1000)
  if (local.getUTCDate() > 25 || (local.getUTCDate() === 25 && local.getUTCHours() >= 17)) {
    local.setUTCDate(1)
    local.setUTCMonth(local.getUTCMonth() + 1)
  }
  return local.toISOString().slice(0, 7)
}
