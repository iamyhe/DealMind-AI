/**
 * Mock Mode data layer — mirrors the FastAPI contract exactly.
 *
 * Every number here is REAL: generated read-only from data/dealmind.db by
 * frontend/scripts/generate_mock_data.py (funnel_summary + 100 curated Feb-2020 replay sessions).
 * Outcome data lives in a separate module that is dynamically imported ONLY on "Reveal outcome".
 */
import { ApiError } from './errors'
import { MOCK_SUMMARIES } from './mock/summaries'
import { MOCK_REPLAY_EVENTS, MOCK_REPLAY_SESSIONS } from './mock/replaySessions'

const delay = (min = 120, max = 320) => new Promise((r) => setTimeout(r, min + Math.random() * (max - min)))

const httpError = (status, detail) => new ApiError(detail, { status, detail })

export async function getSummary(period) {
  await delay()
  const s = MOCK_SUMMARIES[period]
  if (!s) throw httpError(422, `Unsupported period "${period}"`)
  return { ...s }
}

export async function getReplaySessions(page = 1, size = 20) {
  await delay()
  const p = Math.max(1, Number(page) || 1)
  const sz = Math.min(100, Math.max(1, Number(size) || 20))
  const start = (p - 1) * sz
  return {
    items: MOCK_REPLAY_SESSIONS.slice(start, start + sz).map((s) => ({ ...s })),
    page: p,
    size: sz,
    total: MOCK_REPLAY_SESSIONS.length,
  }
}

export async function getReplaySession(id) {
  await delay()
  const session = MOCK_REPLAY_SESSIONS.find((s) => s.id === id)
  if (!session) throw httpError(404, 'Session not found')
  return { session: { ...session }, events: (MOCK_REPLAY_EVENTS[id] ?? []).map((e) => ({ ...e })) }
}

/** Hidden outcome — module is code-split and only fetched by the browser on explicit reveal. */
export async function getReplayOutcome(id) {
  await delay(250, 500)
  const { MOCK_REPLAY_OUTCOMES } = await import('./mock/replayOutcomes')
  const o = MOCK_REPLAY_OUTCOMES[id]
  if (!o) throw httpError(404, 'Session not found')
  return { actual_outcome: o.actual_outcome, events: o.events.map((e) => ({ ...e })) }
}

/** Mirrors the current backend: POST /api/predict -> HTTP 501. Never fabricates a score. */
export async function predict() {
  await delay(150, 300)
  throw httpError(501, 'Not implemented')
}

export const MOCK_TOTAL_SESSIONS = MOCK_REPLAY_SESSIONS.length
export { MOCK_SUMMARIES }
