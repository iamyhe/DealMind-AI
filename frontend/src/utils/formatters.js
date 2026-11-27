/**
 * Display formatters. Rules:
 *  - Percent inputs are ALREADY percentages (87.19 -> "87.19%"); never multiplied by 100.
 *  - Prices are recorded source price units: NO currency symbol is ever added.
 *  - All timestamps are UTC ("YYYY-MM-DD HH:MM:SS+00") and are labelled as UTC.
 */
const EMPTY = '—'

const isNil = (v) => v === null || v === undefined || v === '' || (typeof v === 'number' && Number.isNaN(v))

const intFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

export function formatInt(n) {
  if (isNil(n)) return EMPTY
  const num = Number(n)
  return Number.isFinite(num) ? intFmt.format(Math.round(num)) : EMPTY
}

export function formatNumber(n, digits = 2) {
  if (isNil(n)) return EMPTY
  const num = Number(n)
  if (!Number.isFinite(num)) return EMPTY
  return num.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

/** 87.19 -> "87.19%" (input already a percentage). */
export function formatPct(n, digits = 2) {
  if (isNil(n)) return EMPTY
  return `${formatNumber(n, digits)}%`
}

/** 0.1257 -> "12.57%" (input is a 0..1 ratio; used for report JSON shares/rates). */
export function formatRatioPct(r, digits = 2) {
  if (isNil(r)) return EMPTY
  return formatPct(Number(r) * 100, digits)
}

/** 40.82 -> "40.82" — recorded price units, no currency. */
export function formatPriceUnits(n, digits = 2) {
  if (isNil(n)) return EMPTY
  return formatNumber(n, digits)
}

/** 0.4357 -> "0.44x" */
export function formatRatio(n, digits = 2) {
  if (isNil(n)) return EMPTY
  return `${formatNumber(n, digits)}x`
}

/** Model metric (0..1) -> "0.191" */
export function formatMetric(n, digits = 3) {
  if (isNil(n)) return EMPTY
  return Number(n).toFixed(digits)
}

/** 344 -> "5m 44s", 45 -> "45s", 0 -> "0s", 7322 -> "2h 2m 2s", 90061 -> "1d 1h 1m" */
export function formatDuration(seconds) {
  if (isNil(seconds)) return EMPTY
  let s = Math.max(0, Math.round(Number(seconds)))
  if (!Number.isFinite(s)) return EMPTY
  const d = Math.floor(s / 86400)
  s -= d * 86400
  const h = Math.floor(s / 3600)
  s -= h * 3600
  const m = Math.floor(s / 60)
  s -= m * 60
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

/** 1 -> "Yes", 0 -> "No" */
export function formatBoolInt(v) {
  if (isNil(v)) return EMPTY
  return Number(v) === 1 ? 'Yes' : Number(v) === 0 ? 'No' : String(v)
}

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

/** 0=Sunday ... 6=Saturday */
export function formatWeekday(dow) {
  if (isNil(dow)) return EMPTY
  return WEEKDAYS[Number(dow)] ?? EMPTY
}

/** Parse "2020-02-14 20:03:53+00" (or ISO) into a Date in UTC. */
export function parseUtc(ts) {
  if (isNil(ts)) return null
  if (ts instanceof Date) return ts
  let s = String(ts).trim().replace(' ', 'T')
  if (/[+-]\d{2}$/.test(s)) s += ':00' // "+00" -> "+00:00"
  else if (!/(Z|[+-]\d{2}:?\d{2})$/.test(s)) s += 'Z' // naive -> UTC
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

const pad = (n) => String(n).padStart(2, '0')

/** "2020-02-14 20:03:53 UTC" */
export function formatUtcTime(ts) {
  const d = parseUtc(ts)
  if (!d) return EMPTY
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(
    d.getUTCMinutes(),
  )}:${pad(d.getUTCSeconds())} UTC`
}

/** "20:03:53 UTC" */
export function formatUtcShort(ts) {
  const d = parseUtc(ts)
  if (!d) return EMPTY
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`
}

/** "HH:MM:SS" (no suffix — for dense timelines that carry a UTC header). */
export function formatUtcClock(ts) {
  const d = parseUtc(ts)
  if (!d) return EMPTY
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`
}

/** Weekday name derived from a UTC timestamp. */
export function weekdayOfUtc(ts) {
  const d = parseUtc(ts)
  return d ? WEEKDAYS[d.getUTCDay()] : EMPTY
}

/** Seconds between two UTC timestamps. */
export function secondsBetween(a, b) {
  const da = parseUtc(a)
  const db = parseUtc(b)
  if (!da || !db) return null
  return Math.round((db.getTime() - da.getTime()) / 1000)
}

/** "+5m 44s" style offset label. */
export function formatOffset(seconds) {
  if (isNil(seconds)) return EMPTY
  return `+${formatDuration(seconds)}`
}

export function formatEventType(t) {
  switch (t) {
    case 'view':
      return 'VIEW'
    case 'cart':
      return 'CART'
    case 'remove_from_cart':
      return 'REMOVE'
    case 'purchase':
      return 'PURCHASE'
    default:
      return String(t ?? EMPTY).toUpperCase()
  }
}

/** Human labels for snake_case feature names. */
export function humanizeFeature(name) {
  return String(name)
    .replace(/_utc$/, ' (UTC)')
    .replace(/_at_first_cart_sec/, ' at first cart')
    .replace(/_before_cart/, ' before cart')
    .replace(/_/g, ' ')
    .replace(/^\w/, (c) => c.toUpperCase())
}

export { EMPTY }
