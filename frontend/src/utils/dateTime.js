const API_TIMEZONE_SUFFIX = /(?:Z|[+-]\d{2}:\d{2})$/i

export function parseApiDateTime(value) {
  if (!value) return null
  const raw = String(value).trim()
  if (!raw) return null

  // PostgreSQL currently returns timestamps without an offset. Render stores
  // those values in UTC, so make the zone explicit before formatting them.
  const parsed = new Date(API_TIMEZONE_SUFFIX.test(raw) ? raw : `${raw}Z`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function formatJohannesburgDateTime(value, fallback = 'n/a') {
  const parsed = parseApiDateTime(value)
  if (!parsed) return fallback

  return parsed.toLocaleString('en-ZA', {
    timeZone: 'Africa/Johannesburg',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZoneName: 'short',
  })
}
