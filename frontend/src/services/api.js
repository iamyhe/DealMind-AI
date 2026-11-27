/**
 * DealMind AI API client.
 * Targets `VITE_API_BASE_URL || http://localhost:8000` (overridable in the Settings popover)
 * and transparently falls back to bundled mock data in Auto mode when the API is unreachable.
 *
 * Zero-leakage guarantees enforced client-side:
 *  - Replay detail events are filtered to SAFE phases only (pre-cart + first-cart second).
 *  - The /outcome endpoint is only ever called from revealOutcome() (explicit user click).
 *  - /api/predict 501 is surfaced as a "pending" state; no prediction is ever invented.
 */
import {
  checkConnection,
  markUnreachable,
  onHealthCheck,
  registerCache,
  resolveSource,
  settings,
} from './config'
import * as mock from './mockData'
import { ApiError } from './errors'
import { PREDICT_FEATURES, SAFE_EVENT_PHASES } from '@/utils/sessionSchema'

export const PERIODS = ['ALL', '2019-10', '2019-11', '2019-12', '2020-01', '2020-02']
export const MONTHLY_PERIODS = PERIODS.slice(1)

export { ApiError }

function url(path) {
  return `${settings.baseUrl}${path}`
}

async function request(path, { method = 'GET', body, timeout = 8000 } = {}) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeout)
  let res
  try {
    res = await fetch(url(path), {
      method,
      headers: body ? { 'Content-Type': 'application/json', Accept: 'application/json' } : { Accept: 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    })
  } catch (e) {
    const timedOut = e?.name === 'AbortError'
    throw new ApiError(timedOut ? 'Request timed out' : 'Network error — API unreachable', { network: true })
  } finally {
    clearTimeout(timer)
  }

  let data = null
  const text = await res.text()
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { detail: text }
    }
  }
  if (!res.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : data?.detail ? JSON.stringify(data.detail) : null
    throw new ApiError(detail || `HTTP ${res.status}`, { status: res.status, detail })
  }
  return data
}

/** Route a call to live API or mock according to the current mode. */
async function route(liveFn, mockFn) {
  const source = await resolveSource()
  if (source === 'mock') return mockFn()
  try {
    return await liveFn()
  } catch (e) {
    if (e instanceof ApiError && e.network && settings.mode === 'auto') {
      markUnreachable(e)
      return mockFn()
    }
    throw e
  }
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------
export async function getHealth() {
  const data = await request('/api/health', { timeout: 3000 })
  return data?.status === 'ok'
}
onHealthCheck(() => getHealth().catch(() => false))

export { checkConnection }

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------
const SUMMARY_FIELDS = [
  'period',
  'total_valid_sessions',
  'sessions_with_view',
  'sessions_with_cart',
  'sessions_with_purchase',
  'overall_purchase_rate_pct',
  'view_to_purchase_rate_pct',
  'session_cart_abandonment_rate_pct',
  'historical_aov_pos',
  'historical_aov_signed',
]

const summaryCache = new Map()
registerCache(() => summaryCache.clear())

function pickSummary(data, period) {
  const out = {}
  for (const k of SUMMARY_FIELDS) out[k] = data?.[k] ?? null
  out.period = out.period ?? period
  return out
}

export function getSummary(period = 'ALL') {
  if (!PERIODS.includes(period)) return Promise.reject(new ApiError(`Unsupported period "${period}"`, { status: 422 }))
  if (summaryCache.has(period)) return summaryCache.get(period)
  const p = route(
    () => request(`/api/summary?period=${encodeURIComponent(period)}`),
    () => mock.getSummary(period),
  )
    .then((d) => pickSummary(d, period))
    .catch((e) => {
      summaryCache.delete(period)
      throw e
    })
  summaryCache.set(period, p)
  return p
}

/** All 5 monthly periods fetched in parallel (cached). */
export function getMonthlySummaries() {
  return Promise.all(MONTHLY_PERIODS.map((p) => getSummary(p)))
}

// ---------------------------------------------------------------------------
// Replay sessions
// ---------------------------------------------------------------------------
export async function getReplaySessions(page = 1, size = 20) {
  const data = await route(
    () => request(`/api/replay-sessions?page=${page}&size=${size}`),
    () => mock.getReplaySessions(page, size),
  )
  const items = data?.items ?? data?.sessions ?? []
  return {
    items: items.map(sanitizeSession),
    page: Number(data?.page ?? page),
    size: Number(data?.size ?? size),
    total: Number(data?.total ?? items.length),
  }
}

const FORBIDDEN_KEYS = ['user_id', 'user_session', 'target_purchased_after_cart', 'actual_outcome']
function sanitizeSession(s) {
  if (!s || typeof s !== 'object') return s
  const clean = { ...s }
  for (const k of FORBIDDEN_KEYS) delete clean[k]
  return clean
}

function sanitizeEvent(e) {
  const { id, event_time, event_type, product_id, category_id, category_code, brand, price, event_phase } = e ?? {}
  return { id, event_time, event_type, product_id, category_id, category_code, brand, price, event_phase }
}

export async function getReplaySession(id) {
  const data = await route(
    () => request(`/api/replay-sessions/${encodeURIComponent(id)}`),
    () => mock.getReplaySession(id),
  )
  const events = (data?.events ?? [])
    .filter((e) => SAFE_EVENT_PHASES.includes(e?.event_phase)) // never render post-cart events here
    .map(sanitizeEvent)
  return { session: sanitizeSession(data?.session ?? null), events }
}

/** Defensive extractor for the post-cart events array (key name may vary across backend versions). */
export function extractOutcomeEvents(data) {
  const arr = data?.events ?? data?.outcome_events ?? data?.post_cart_events ?? data?.hidden_events ?? []
  return Array.isArray(arr) ? arr.map(sanitizeEvent) : []
}

/**
 * ONLY call from an explicit "Reveal outcome" user action.
 * Returns { actualOutcome: 0|1|null, events: [...] }.
 */
export async function revealOutcome(id) {
  const data = await route(
    () => request(`/api/replay-sessions/${encodeURIComponent(id)}/outcome`),
    () => mock.getReplayOutcome(id),
  )
  const raw = data?.actual_outcome ?? data?.outcome ?? null
  const actualOutcome = raw === 0 || raw === 1 ? raw : raw === '0' || raw === '1' ? Number(raw) : null
  const events = extractOutcomeEvents(data).sort((a, b) => String(a.event_time).localeCompare(String(b.event_time)))
  return { actualOutcome, events }
}

// ---------------------------------------------------------------------------
// Prediction
// ---------------------------------------------------------------------------
export function buildPredictPayload(session) {
  const payload = {}
  for (const f of PREDICT_FEATURES) payload[f] = session?.[f] ?? null
  return payload
}

function normalizePrediction(data) {
  const prob = data?.probability ?? data?.purchase_probability ?? data?.score ?? null
  const cls = data?.prediction ?? data?.label ?? data?.predicted_class ?? null
  const probability = prob === null || prob === undefined || Number.isNaN(Number(prob)) ? null : Number(prob)
  const threshold = data?.threshold === undefined || data?.threshold === null ? null : Number(data.threshold)
  let prediction = cls === null || cls === undefined ? null : Number(cls)
  if (prediction !== 0 && prediction !== 1) prediction = null
  if (prediction === null && probability !== null && threshold !== null) prediction = probability >= threshold ? 1 : 0
  return {
    status: probability === null && prediction === null ? 'pending' : 'ok',
    httpStatus: 200,
    probability,
    prediction,
    threshold,
    modelVersion: data?.model_version ?? null,
    detail: probability === null && prediction === null ? 'Response contained no score' : null,
  }
}

/** Never throws. Returns { status: 'ok' | 'pending' | 'error', ... } */
export async function predict(session) {
  const payload = buildPredictPayload(session)
  try {
    const data = await route(
      () => request('/api/predict', { method: 'POST', body: payload }),
      () => mock.predict(payload),
    )
    return normalizePrediction(data)
  } catch (e) {
    if (e instanceof ApiError && e.status === 501) {
      return { status: 'pending', httpStatus: 501, detail: 'Model integration pending' }
    }
    return {
      status: 'error',
      httpStatus: e?.status ?? 0,
      detail: e?.network ? 'API unreachable' : e?.message || 'Prediction request failed',
    }
  }
}
