<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SessionBasketPathSvg from '@/components/SessionBasketPathSvg.vue'
import StateError from '@/components/StateError.vue'
import StateLoading from '@/components/StateLoading.vue'
import { getReplaySession, getReplaySessions, predict, revealOutcome } from '@/services/api'
import { settings } from '@/services/config'
import {
  formatDuration,
  formatEventType,
  formatInt,
  formatNumber,
  formatOffset,
  formatPriceUnits,
  formatRatio,
  formatUtcClock,
  formatUtcTime,
  secondsBetween,
  weekdayOfUtc,
} from '@/utils/formatters'
import { SESSION_FIELDS } from '@/utils/sessionSchema'

const PAGE_SIZE = 20

const route = useRoute()
const router = useRouter()

// Sidebar list state
const page = ref(1)
const total = ref(100)
const items = ref([])
const listLoading = ref(true)
const listError = ref(null)
const query = ref('')

// Selected session detail state
const activeId = ref('')
const session = ref(null)
const safeEvents = ref([])
const detailLoading = ref(false)
const detailError = ref(null)
const notFound = ref(false)

// Prediction state (POST /api/predict)
const prediction = ref(null)
const predictLoading = ref(false)

// STRICT ZERO-LEAKAGE: hidden until the user explicitly clicks "Reveal outcome"
const revealed = ref(false)
const actualOutcome = ref(null)
const postEvents = ref([])
const outcomeLoading = ref(false)
const outcomeError = ref(null)

// Features accordion (closed by default)
const featuresOpen = ref(false)

let detailSeq = 0

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

const filteredItems = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return items.value
  return items.value.filter((s) => s.id.toLowerCase().includes(q))
})

const sessionIndexInPage = computed(() => items.value.findIndex((s) => s.id === activeId.value))
const prevSessionId = computed(() => {
  const idx = sessionIndexInPage.value
  if (idx > 0) return items.value[idx - 1].id
  return null
})
const nextSessionId = computed(() => {
  const idx = sessionIndexInPage.value
  if (idx >= 0 && idx < items.value.length - 1) return items.value[idx + 1].id
  return null
})

const groupedFeatures = computed(() => {
  if (!session.value) return []
  const groups = new Map()
  for (const f of SESSION_FIELDS) {
    if (!groups.has(f.group)) groups.set(f.group, [])
    groups.get(f.group).push({ ...f, formatted: f.fmt(session.value[f.key]) })
  }
  return Array.from(groups.entries()).map(([group, fields]) => ({ group, fields }))
})

function pageForSessionId(id) {
  const m = /^rs_(\d+)$/i.exec(String(id || '').trim())
  if (!m) return 1
  const n = Number(m[1])
  if (!Number.isFinite(n) || n < 1) return 1
  return Math.min(5, Math.ceil(n / PAGE_SIZE))
}

function resetOutcomeAndPrediction() {
  revealed.value = false
  actualOutcome.value = null
  postEvents.value = []
  outcomeLoading.value = false
  outcomeError.value = null
  prediction.value = null
  predictLoading.value = false
}

async function fetchPage(targetPage) {
  listLoading.value = true
  listError.value = null
  try {
    const res = await getReplaySessions(targetPage, PAGE_SIZE)
    items.value = res.items
    page.value = res.page
    total.value = res.total
  } catch (e) {
    listError.value = e?.message || 'Unable to load replay sessions'
  } finally {
    listLoading.value = false
  }
}

async function loadDetail(id) {
  const seq = ++detailSeq
  activeId.value = id
  resetOutcomeAndPrediction()
  detailLoading.value = true
  detailError.value = null
  notFound.value = false
  session.value = null
  safeEvents.value = []

  try {
    const res = await getReplaySession(id)
    if (seq !== detailSeq) return
    session.value = res.session
    safeEvents.value = res.events
    detailLoading.value = false

    // Score via POST /api/predict (non-blocking; gracefully handles unavailable predictions)
    predictLoading.value = true
    const pred = await predict(res.session)
    if (seq !== detailSeq) return
    prediction.value = pred
  } catch (e) {
    if (seq !== detailSeq) return
    if (e?.status === 404) {
      notFound.value = true
    } else {
      detailError.value = e?.message || 'Unable to load replay session'
    }
    detailLoading.value = false
  } finally {
    if (seq === detailSeq) predictLoading.value = false
  }
}

async function retryPredict() {
  if (!session.value) return
  const seq = detailSeq
  predictLoading.value = true
  const pred = await predict(session.value)
  if (seq === detailSeq) {
    prediction.value = pred
    predictLoading.value = false
  }
}

async function handleReveal() {
  if (!session.value || outcomeLoading.value || revealed.value) return
  const seq = detailSeq
  const id = session.value.id
  outcomeLoading.value = true
  outcomeError.value = null
  try {
    const res = await revealOutcome(id)
    if (seq !== detailSeq) return
    actualOutcome.value = res.actualOutcome
    postEvents.value = res.events
    revealed.value = true
  } catch (e) {
    if (seq !== detailSeq) return
    outcomeError.value = e?.message || 'Failed to reveal outcome'
  } finally {
    if (seq === detailSeq) outcomeLoading.value = false
  }
}

function selectSession(id) {
  if (!id) return
  if (route.params.id === id) {
    loadDetail(id)
  } else {
    router.push({ name: 'replay', params: { id } })
  }
}

function goPage(nextPage) {
  if (nextPage < 1 || nextPage > totalPages.value || nextPage === page.value) return
  fetchPage(nextPage)
}

function sparkPoints(s) {
  const views = Math.min(Number(s?.views_before_cart ?? 0), 8)
  const y0 = views === 0 ? 15 : Math.max(6, 17 - views * 1.4)
  const y1 = 10 + ((Number(s?.removes_before_cart ?? 0) > 0) ? 4 : -2)
  const y2 = 13
  return {
    path: `M 4 ${y0} C 24 ${y0}, 32 ${y1}, 52 ${y2} C 64 ${y2}, 74 14, 88 14`,
    y0,
    y1,
    y2,
  }
}

function eventBadgeClass(ev) {
  if (ev.event_type === 'cart') return 'ev-cart'
  if (ev.event_type === 'purchase') return 'ev-purchase'
  if (ev.event_type === 'remove_from_cart') return 'ev-remove'
  return 'ev-view'
}

const predictionAgreement = computed(() => {
  if (!revealed.value || prediction.value?.status !== 'ok' || prediction.value.prediction === null) return null
  return prediction.value.prediction === actualOutcome.value ? 'match' : 'mismatch'
})

const predictionMessage = computed(() => {
  if (prediction.value?.prediction === 1) {
    return 'Class 1 indicates higher purchase likelihood; it does not guarantee a purchase.'
  }
  if (prediction.value?.prediction === 0) {
    return 'Class 0 indicates lower purchase likelihood / potential abandonment risk; it is not confirmed abandonment.'
  }
  return 'Model score is shown without a predicted class.'
})

async function initRoute() {
  const routeId = route.params.id ? String(route.params.id) : ''
  const targetPage = routeId ? pageForSessionId(routeId) : 1
  await fetchPage(targetPage)
  const initialId = routeId || items.value[0]?.id || 'rs_001'
  if (!routeId) {
    router.replace({ name: 'replay', params: { id: initialId } })
  } else {
    loadDetail(initialId)
  }
}

onMounted(initRoute)

watch(
  () => route.params.id,
  (newId) => {
    const id = newId ? String(newId) : ''
    if (!id) {
      const fallback = items.value[0]?.id || 'rs_001'
      router.replace({ name: 'replay', params: { id: fallback } })
      return
    }
    const targetPage = pageForSessionId(id)
    if (targetPage !== page.value && /^rs_\d+$/i.test(id)) {
      fetchPage(targetPage)
    }
    if (id !== activeId.value) loadDetail(id)
  },
)

watch(
  () => settings.dataVersion,
  () => {
    fetchPage(page.value)
    if (activeId.value) loadDetail(activeId.value)
  },
)
</script>

<template>
  <div class="page replay-page">
    <div class="replay-layout">
      <!-- LEFT SIDEBAR: Replay sessions master list -->
      <aside class="sidebar card" aria-label="Replay sessions list">
        <div class="sb-top">
          <h2 class="sb-title">Replay sessions</h2>
          <p class="sb-sub">Select a session to inspect its basket path ({{ formatInt(total) }} curated cases).</p>

          <div class="search-box">
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" stroke-linecap="round" />
            </svg>
            <input
              v-model="query"
              type="search"
              placeholder="Filter page by rs_… ID"
              aria-label="Filter sessions on current page"
            />
          </div>
        </div>

        <div class="sb-list">
          <StateLoading v-if="listLoading" variant="replay-list" />
          <StateError v-else-if="listError" :message="listError" @retry="fetchPage(page)" />
          <template v-else>
            <button
              v-for="item in filteredItems"
              :key="item.id"
              type="button"
              class="session-row"
              :class="{ active: item.id === activeId }"
              @click="selectSession(item.id)"
            >
              <div class="sr-top">
                <span class="sr-id num">{{ item.id }}</span>
                <span class="sr-chev" aria-hidden="true">›</span>
              </div>

              <!-- Mini basket path sparkline -->
              <svg class="spark" viewBox="0 0 94 22" fill="none" aria-hidden="true">
                <path
                  :d="sparkPoints(item).path"
                  :stroke="item.id === activeId ? 'rgba(255,255,255,0.65)' : '#475569'"
                  stroke-width="1.4"
                  stroke-linecap="round"
                />
                <circle cx="8" :cy="sparkPoints(item).y0" r="2.7" :fill="item.id === activeId ? '#93C5FD' : '#3B82F6'" />
                <circle cx="30" :cy="sparkPoints(item).y1" r="2.2" :fill="item.id === activeId ? '#E2E8F0' : '#60A5FA'" />
                <circle cx="52" :cy="sparkPoints(item).y2" r="3" fill="#D9F936" />
                <circle cx="84" cy="14" r="2.6" :fill="item.id === activeId ? '#FDBA74' : '#F97316'" fill-opacity="0.8" />
              </svg>

              <div class="sr-meta num">
                {{ formatInt(item.views_before_cart) }} views · Cart {{ formatPriceUnits(item.avg_cart_price_at_first_cart_sec) }} ·
                {{ formatDuration(item.seconds_to_first_cart) }}
              </div>
            </button>

            <div v-if="!filteredItems.length" class="empty-filter">
              No sessions matching "{{ query }}" on page {{ page }}.
            </div>
          </template>
        </div>

        <div class="sb-pager">
          <button type="button" class="btn btn-sm" :disabled="page <= 1 || listLoading" @click="goPage(page - 1)">
            ← Prev
          </button>
          <span class="pager-info num">Page {{ page }} of {{ totalPages }}</span>
          <button type="button" class="btn btn-sm" :disabled="page >= totalPages || listLoading" @click="goPage(page + 1)">
            Next →
          </button>
        </div>
      </aside>

      <!-- RIGHT WORKSPACE: Selected session detail -->
      <section class="workspace" aria-live="polite">
        <StateLoading v-if="detailLoading" variant="replay-detail" />

        <div v-else-if="notFound" class="card not-found">
          <span class="badge badge-red">HTTP 404</span>
          <h2>Session "{{ activeId }}" not found</h2>
          <p class="secondary">Curated replay sessions run from <span class="mono">rs_001</span> to <span class="mono">rs_100</span>.</p>
          <button type="button" class="btn btn-lime" @click="selectSession('rs_001')">Back to rs_001 →</button>
        </div>

        <StateError v-else-if="detailError" :message="detailError" @retry="loadDetail(activeId)" />

        <template v-else-if="session">
          <!-- Session Header -->
          <div class="card detail-head">
            <div class="dh-left">
              <div class="dh-title-row">
                <h1 class="dh-id num">{{ session.id }}</h1>
                <span class="dh-sep" aria-hidden="true">|</span>
                <span class="dh-tag">
                  <svg viewBox="0 0 36 28" width="22" height="18" fill="none" aria-hidden="true">
                    <path d="M12 10 L15 4 H21 L24 10" stroke="#94A3B8" stroke-width="1.8" stroke-linecap="round" />
                    <path d="M3 10 H33 L29.5 24 Q29 25.5 27 25.5 H9 Q7 25.5 6.5 24 Z" stroke="#94A3B8" stroke-width="1.8" />
                    <path d="M5 16 H31 M12 10 L13 25.5 M24 10 L23 25.5" stroke="#64748B" stroke-width="1.1" />
                  </svg>
                  Session replay
                </span>
              </div>
              <p class="dh-sub num">
                {{ weekdayOfUtc(session.session_start) }} · {{ formatUtcTime(session.session_start) }}
                <span class="muted">· First cart {{ formatUtcClock(session.first_cart_time) }} UTC</span>
              </p>
            </div>

            <div class="dh-actions">
              <button type="button" class="btn btn-sm" :disabled="!prevSessionId" @click="selectSession(prevSessionId)">
                ‹ Prev
              </button>
              <button type="button" class="btn btn-sm" :disabled="!nextSessionId" @click="selectSession(nextSessionId)">
                Next ›
              </button>
            </div>
          </div>

          <!-- 5 Quick Feature Pills -->
          <div class="pills-row">
            <div class="pill-card">
              <div class="pill-k">Time to Cart</div>
              <div class="pill-v num">{{ formatDuration(session.seconds_to_first_cart) }}</div>
            </div>
            <div class="pill-card">
              <div class="pill-k">Views Before Cart</div>
              <div class="pill-v num">{{ formatInt(session.views_before_cart) }}</div>
            </div>
            <div class="pill-card">
              <div class="pill-k">Cart Price (Units)</div>
              <div class="pill-v num">{{ formatPriceUnits(session.avg_cart_price_at_first_cart_sec) }}</div>
            </div>
            <div class="pill-card">
              <div class="pill-k">Cart / View Ratio</div>
              <div class="pill-v num">{{ formatRatio(session.price_ratio_cart_to_view) }}</div>
            </div>
            <div class="pill-card">
              <div class="pill-k">User History</div>
              <div class="pill-v num">
                {{ formatInt(session.user_prior_sessions) }} prior · {{ formatInt(session.user_prior_purchase_sessions) }} buys
              </div>
            </div>
          </div>

          <!-- HERO VISUAL: 3-zone session wireframe basket -->
          <div class="card hero-basket-card">
            <SessionBasketPathSvg
              :session="session"
              :safe-events="safeEvents"
              :revealed="revealed"
              :actual-outcome="actualOutcome"
              :post-events="postEvents"
            />
          </div>

          <!-- Zero-Leakage Event Timeline -->
          <div class="card timeline-card">
            <div class="card-head">
              <div>
                <h2 class="card-title">Event timeline (zero-leakage replay)</h2>
                <p class="card-sub">
                  Strictly pre-cart &amp; first-cart snapshot events until outcome reveal · All timestamps in UTC
                </p>
              </div>
              <span class="badge badge-blue num">{{ safeEvents.length }} safe events</span>
            </div>

            <div class="timeline">
              <div v-if="session.views_before_cart === 0 && session.removes_before_cart === 0" class="direct-callout">
                No pre-cart events recorded — user added directly to cart at session start.
              </div>

              <!-- Safe pre-cart & first-cart events -->
              <div
                v-for="(ev, idx) in safeEvents"
                :key="ev.id ?? idx"
                class="tl-row"
                :class="{ 'is-first-cart': ev.event_phase === 'at_first_cart_second' }"
              >
                <div class="tl-rail">
                  <span class="tl-dot" :class="eventBadgeClass(ev)" />
                </div>
                <div class="tl-pill-col">
                  <span class="ev-pill" :class="eventBadgeClass(ev)">{{ formatEventType(ev.event_type) }}</span>
                </div>
                <div class="tl-main">
                  <div class="tl-prod">
                    <span class="strong mono">Product #{{ ev.product_id }}</span>
                    <span v-if="ev.event_phase === 'at_first_cart_second'" class="badge badge-lime">First Cart Moment</span>
                    <span v-else-if="ev.event_phase === 'same_second_other'" class="badge">Same-second event</span>
                  </div>
                  <div class="tl-meta">
                    <span>Brand: {{ ev.brand || 'Unlisted' }}</span>
                    <span class="muted">·</span>
                    <span class="num">Price: {{ formatPriceUnits(ev.price) }} units</span>
                    <span v-if="ev.category_code" class="muted">· {{ ev.category_code }}</span>
                  </div>
                </div>
                <div class="tl-time num">
                  <div>{{ formatUtcClock(ev.event_time) }}</div>
                  <div class="muted">{{ formatOffset(secondsBetween(session.session_start, ev.event_time)) }}</div>
                </div>
              </div>

              <!-- Dashed Vivid Orange Prediction Cutoff -->
              <div class="cutoff-line" :class="{ unlocked: revealed }">
                <span class="cutoff-ring" />
                <span class="cutoff-text">
                  {{ revealed ? 'PREDICTION CUTOFF — outcome revealed' : 'PREDICTION CUTOFF — outcome hidden' }}
                </span>
              </div>

              <!-- Post-Cart Zone -->
              <div v-if="!revealed" class="post-locked">
                <div class="lock-row">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <rect x="4" y="11" width="16" height="10" rx="2" />
                    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
                  </svg>
                  <span>Post-cart events are withheld by the API until outcome reveal (Zero-Leakage Guarantee).</span>
                </div>
                <div class="ghost-bars" aria-hidden="true">
                  <div class="ghost-bar" />
                  <div class="ghost-bar short" />
                </div>
              </div>

              <Transition name="rise">
                <div v-if="revealed" class="post-unlocked">
                  <div v-if="!postEvents.length" class="empty-post">
                    No further events recorded after first cart.
                  </div>
                  <div
                    v-for="(ev, idx) in postEvents"
                    :key="ev.id ?? `post-${idx}`"
                    class="tl-row"
                    :class="{ 'is-purchase': ev.event_type === 'purchase' }"
                  >
                    <div class="tl-rail">
                      <span class="tl-dot" :class="eventBadgeClass(ev)" />
                    </div>
                    <div class="tl-pill-col">
                      <span class="ev-pill" :class="eventBadgeClass(ev)">{{ formatEventType(ev.event_type) }}</span>
                    </div>
                    <div class="tl-main">
                      <div class="tl-prod">
                        <span class="strong mono">Product #{{ ev.product_id }}</span>
                        <span v-if="ev.event_type === 'purchase'" class="badge badge-green">Confirmed Purchase</span>
                      </div>
                      <div class="tl-meta">
                        <span>Brand: {{ ev.brand || 'Unlisted' }}</span>
                        <span class="muted">·</span>
                        <span class="num">Price: {{ formatPriceUnits(ev.price) }} units</span>
                      </div>
                    </div>
                    <div class="tl-time num">
                      <div>{{ formatUtcClock(ev.event_time) }}</div>
                      <div class="muted">{{ formatOffset(secondsBetween(session.session_start, ev.event_time)) }}</div>
                    </div>
                  </div>
                </div>
              </Transition>
            </div>
          </div>

          <!-- Bottom Two-Column Decision & Verification Cards -->
          <div class="decision-grid">
            <!-- Left: Model prediction (POST /api/predict) -->
            <article class="card decision-card">
              <h2 class="card-title">Model prediction</h2>

              <div v-if="predictLoading" class="pending-box">
                <div class="skeleton" style="width: 44px; height: 44px; border-radius: 10px" />
                <div style="flex: 1">
                  <div class="skeleton" style="width: 60%; height: 15px" />
                  <div class="skeleton" style="width: 85%; height: 12px; margin-top: 8px" />
                </div>
              </div>

              <div v-else-if="prediction?.status === 'pending'" class="pending-box">
                <div class="node-icon-box" aria-hidden="true">
                  <svg viewBox="0 0 28 28" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8">
                    <path d="M5 20 L11 12 L17 16 L23 8" stroke-linecap="round" stroke-linejoin="round" />
                    <circle cx="5" cy="20" r="2" fill="#0B0E14" />
                    <circle cx="11" cy="12" r="2" fill="#0B0E14" />
                    <circle cx="17" cy="16" r="2" fill="#0B0E14" />
                    <circle cx="23" cy="8" r="2" fill="#0B0E14" />
                  </svg>
                </div>
                <div>
                  <div class="pending-title">Prediction pending</div>
                  <p class="pending-desc">
                    No score is shown until the model returns one; nothing is fabricated.
                  </p>
                </div>
              </div>

              <div v-else-if="prediction?.status === 'error'" class="pending-box">
                <div>
                  <div class="pending-title">Prediction unavailable</div>
                  <p class="pending-desc">{{ prediction.detail }}</p>
                  <button type="button" class="btn btn-sm" style="margin-top: 10px" @click="retryPredict">
                    Retry /api/predict
                  </button>
                </div>
              </div>

              <div v-else-if="prediction?.status === 'ok'" class="pred-ready">
                <div class="pred-top">
                  <span
                    v-if="prediction.prediction !== null && prediction.prediction !== undefined"
                    class="badge"
                    :class="prediction.prediction === 1 ? 'badge-green' : 'badge-orange'"
                  >
                    Predicted class {{ prediction.prediction }}
                  </span>
                  <span v-else class="muted">Predicted class unavailable</span>
                  <span v-if="prediction.modelVersion" class="muted mono">{{ prediction.modelVersion }}</span>
                </div>
                <div
                  v-if="prediction.modelScore !== null && prediction.modelScore !== undefined"
                  class="prob-block"
                >
                  <div class="prob-row">
                    <span>Model Score (Uncalibrated)</span>
                    <strong class="num">{{ formatNumber(prediction.modelScore, 4) }}</strong>
                  </div>
                </div>
                <p class="pending-desc">{{ predictionMessage }}</p>
              </div>
            </article>

            <!-- Right: Actual outcome (GET /api/replay-sessions/{id}/outcome) -->
            <article class="card decision-card">
              <h2 class="card-title">Actual outcome</h2>

              <template v-if="!revealed">
                <div class="outcome-locked">
                  <div class="outcome-lock-head">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                      <rect x="4" y="11" width="16" height="10" rx="2" />
                      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
                    </svg>
                    <strong>Outcome hidden</strong>
                  </div>
                  <p class="pending-desc">
                    Reveal the true historical session outcome and post-cart timeline.
                  </p>
                </div>

                <p v-if="outcomeError" class="err-inline">{{ outcomeError }}</p>

                <button
                  type="button"
                  class="btn btn-lime btn-block reveal-btn"
                  :disabled="outcomeLoading"
                  @click="handleReveal"
                >
                  {{ outcomeLoading ? 'Revealing outcome…' : 'Reveal outcome →' }}
                </button>
              </template>

              <Transition name="rise">
                <div v-if="revealed" class="outcome-revealed">
                  <div class="verdict-row">
                    <span class="verdict-badge" :class="actualOutcome === 1 ? 'v-buy' : 'v-abandon'">
                      {{ actualOutcome === 1 ? 'Purchased After Cart (1)' : 'Abandoned Cart (0)' }}
                    </span>
                    <span
                      v-if="predictionAgreement"
                      class="badge"
                      :class="predictionAgreement === 'match' ? 'badge-green' : 'badge-amber'"
                    >
                      {{ predictionAgreement === 'match' ? 'Matches prediction' : 'Differs from prediction' }}
                    </span>
                  </div>
                  <p class="pending-desc num">
                    Unlocked {{ formatInt(postEvents.length) }} post-cart event{{ postEvents.length === 1 ? '' : 's' }}
                    in the timeline above. Switching sessions automatically re-locks this panel.
                  </p>
                </div>
              </Transition>
            </article>
          </div>

          <!-- Collapsible 25-Feature Inspector Accordion (closed by default) -->
          <div class="card accordion-card">
            <button
              type="button"
              class="acc-trigger"
              :aria-expanded="featuresOpen"
              @click="featuresOpen = !featuresOpen"
            >
              <div>
                <span class="card-title">Inspect all 25 session features</span>
                <span class="acc-sub">Safe snapshot captured at first cart moment (no post-cart leakage)</span>
              </div>
              <span class="acc-chev" :class="{ open: featuresOpen }" aria-hidden="true">⌄</span>
            </button>

            <Transition name="rise">
              <div v-if="featuresOpen" class="acc-body">
                <div v-for="grp in groupedFeatures" :key="grp.group" class="feat-group">
                  <div class="eyebrow">{{ grp.group }}</div>
                  <div class="feat-grid">
                    <div v-for="f in grp.fields" :key="f.key" class="feat-item">
                      <span class="feat-k">{{ f.label }}</span>
                      <span class="feat-v num">{{ f.formatted }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </Transition>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
.replay-layout {
  display: grid;
  grid-template-columns: 332px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

/* Left Sidebar */
.sidebar {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: sticky;
  top: 76px;
  max-height: calc(100vh - 96px);
}
.sb-title {
  font-size: 1.3rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.sb-sub {
  font-size: 0.78rem;
  color: var(--text-2);
  margin-top: 4px;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 11px;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: var(--bg-canvas);
  color: var(--text-3);
}
.search-box input {
  border: none;
  background: none;
  width: 100%;
  font-size: 0.8rem;
  color: var(--text);
}
.search-box input:focus {
  outline: none;
}

.sb-list {
  display: flex;
  flex-direction: column;
  gap: 9px;
  overflow-y: auto;
  padding-right: 4px;
  min-height: 240px;
}

.session-row {
  text-align: left;
  padding: 12px 13px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--bg-card-2);
  display: flex;
  flex-direction: column;
  gap: 5px;
  transition: background 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}
.session-row:hover {
  border-color: var(--border-hover);
  background: #141b29;
}
.session-row.active {
  background: var(--browse);
  border-color: #60a5fa;
  box-shadow: 0 8px 26px rgba(37, 99, 235, 0.34);
}
.sr-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.sr-id {
  font-size: 0.96rem;
  font-weight: 700;
  color: var(--text);
}
.sr-chev {
  font-size: 1.1rem;
  color: var(--text-2);
  line-height: 1;
}
.session-row.active .sr-chev {
  color: #fff;
}
.spark {
  width: 96px;
  height: 22px;
}
.sr-meta {
  font-size: 0.72rem;
  color: var(--text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-row.active .sr-meta {
  color: rgba(255, 255, 255, 0.88);
}

.empty-filter {
  padding: 18px 10px;
  text-align: center;
  font-size: 0.8rem;
  color: var(--text-3);
}

.sb-pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
.pager-info {
  font-size: 0.76rem;
  color: var(--text-2);
}

/* Right Workspace */
.workspace {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.not-found {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  padding: 28px;
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}
.dh-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.dh-id {
  font-size: 1.6rem;
  font-weight: 700;
  letter-spacing: -0.025em;
}
.dh-sep {
  color: var(--text-3);
  font-weight: 300;
}
.dh-tag {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 0.94rem;
  color: var(--text-2);
  font-weight: 500;
}
.dh-sub {
  font-size: 0.8rem;
  color: var(--text-2);
  margin-top: 4px;
}
.dh-actions {
  display: flex;
  gap: 6px;
}

/* Quick Feature Pills */
.pills-row {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}
.pill-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 11px 13px;
}
.pill-k {
  font-size: 0.69rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-3);
}
.pill-v {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text);
  margin-top: 3px;
}

.hero-basket-card {
  padding: 16px 20px;
}

/* Timeline */
.timeline {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.direct-callout {
  padding: 9px 12px;
  border-radius: 9px;
  border: 1px dashed var(--border-hover);
  background: var(--bg-card-2);
  font-size: 0.8rem;
  color: var(--text-2);
  margin-bottom: 6px;
}
.tl-row {
  display: grid;
  grid-template-columns: 20px 84px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 9px 10px;
  border-radius: 10px;
  transition: background 0.15s ease;
}
.tl-row:hover {
  background: rgba(255, 255, 255, 0.02);
}
.tl-row.is-first-cart {
  background: rgba(217, 249, 54, 0.045);
  border: 1px solid rgba(217, 249, 54, 0.18);
}
.tl-row.is-purchase {
  background: rgba(34, 197, 94, 0.07);
  border: 1px solid rgba(34, 197, 94, 0.28);
}

.tl-rail {
  display: flex;
  justify-content: center;
  position: relative;
}
.tl-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  border: 2px solid var(--bg-card);
}
.tl-dot.ev-view {
  background: var(--browse-2);
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.7);
}
.tl-dot.ev-cart {
  background: var(--cart);
  box-shadow: 0 0 10px rgba(217, 249, 54, 0.85);
}
.tl-dot.ev-remove {
  background: var(--warning);
}
.tl-dot.ev-purchase {
  background: var(--success);
  box-shadow: 0 0 10px rgba(34, 197, 94, 0.85);
}

.ev-pill {
  display: inline-block;
  width: 78px;
  text-align: center;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  border: 1px solid transparent;
}
.ev-pill.ev-view {
  color: #93c5fd;
  border-color: rgba(59, 130, 246, 0.45);
  background: rgba(37, 99, 235, 0.14);
}
.ev-pill.ev-cart {
  color: var(--cart);
  border-color: rgba(217, 249, 54, 0.55);
  background: rgba(217, 249, 54, 0.1);
}
.ev-pill.ev-remove {
  color: #fcd34d;
  border-color: rgba(245, 158, 11, 0.45);
  background: rgba(245, 158, 11, 0.1);
}
.ev-pill.ev-purchase {
  color: #4ade80;
  border-color: rgba(34, 197, 94, 0.55);
  background: rgba(34, 197, 94, 0.14);
}

.tl-prod {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 0.84rem;
}
.tl-meta {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
  font-size: 0.75rem;
  color: var(--text-2);
  margin-top: 2px;
}
.tl-time {
  text-align: right;
  font-size: 0.75rem;
  color: var(--text-2);
  white-space: nowrap;
}

/* Prediction Cutoff Line */
.cutoff-line {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 0;
  padding-left: 4px;
}
.cutoff-line::before,
.cutoff-line::after {
  content: '';
  height: 1px;
  border-top: 1.6px dashed var(--outcome);
}
.cutoff-line::before {
  width: 24px;
}
.cutoff-line::after {
  flex: 1;
}
.cutoff-line.unlocked::before,
.cutoff-line.unlocked::after {
  border-top-color: rgba(34, 197, 94, 0.65);
}
.cutoff-ring {
  width: 11px;
  height: 11px;
  border-radius: 999px;
  border: 2px solid var(--outcome);
  background: var(--bg-card);
  flex-shrink: 0;
}
.cutoff-line.unlocked .cutoff-ring {
  border-color: var(--success);
}
.cutoff-text {
  font-size: 0.71rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--outcome);
  white-space: nowrap;
}
.cutoff-line.unlocked .cutoff-text {
  color: #4ade80;
}

/* Locked & Unlocked Post-Cart */
.post-locked {
  padding: 13px 14px;
  border-radius: 11px;
  border: 1px dashed #2a354b;
  background: rgba(7, 10, 15, 0.55);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.lock-row {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 0.79rem;
  color: var(--text-2);
}
.ghost-bars {
  display: flex;
  flex-direction: column;
  gap: 7px;
  opacity: 0.35;
}
.ghost-bar {
  height: 12px;
  border-radius: 6px;
  background: #1d2638;
  width: 72%;
}
.ghost-bar.short {
  width: 48%;
}
.post-unlocked {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.empty-post {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--bg-card-2);
  font-size: 0.82rem;
  color: var(--text-2);
}

/* Bottom Decision Cards */
.decision-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.decision-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.pending-box {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
.node-icon-box {
  width: 46px;
  height: 46px;
  border-radius: 11px;
  border: 1px solid var(--border-hover);
  background: var(--bg-card-2);
  color: var(--text-2);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.pending-title {
  font-size: 0.94rem;
  font-weight: 650;
  color: var(--text);
}
.pending-desc {
  font-size: 0.79rem;
  color: var(--text-2);
  margin-top: 3px;
}

.pred-ready {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pred-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.prob-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.8rem;
  color: var(--text-2);
  margin-bottom: 6px;
}
.outcome-locked {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.outcome-lock-head {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
  font-size: 0.94rem;
}
.reveal-btn {
  margin-top: auto;
  padding: 11px 18px;
  font-size: 0.9rem;
}
.err-inline {
  font-size: 0.78rem;
  color: #fca5a5;
}

.outcome-revealed {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.verdict-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.verdict-badge {
  display: inline-flex;
  align-items: center;
  padding: 6px 13px;
  border-radius: 10px;
  font-size: 0.88rem;
  font-weight: 700;
  border: 1px solid transparent;
}
.v-buy {
  background: rgba(34, 197, 94, 0.14);
  color: #4ade80;
  border-color: rgba(34, 197, 94, 0.45);
}
.v-abandon {
  background: rgba(239, 68, 68, 0.14);
  color: #fca5a5;
  border-color: rgba(239, 68, 68, 0.45);
}

/* Accordion */
.accordion-card {
  padding: 0;
  overflow: hidden;
}
.acc-trigger {
  width: 100%;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  text-align: left;
}
.acc-trigger:hover {
  background: rgba(255, 255, 255, 0.02);
}
.acc-sub {
  display: block;
  font-size: 0.76rem;
  color: var(--text-3);
  margin-top: 2px;
}
.acc-chev {
  font-size: 1.25rem;
  color: var(--text-2);
  transition: transform 0.2s ease;
}
.acc-chev.open {
  transform: rotate(180deg);
}
.acc-body {
  padding: 0 20px 20px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 16px;
}
.feat-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.feat-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 16px;
}
.feat-item {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  padding: 7px 10px;
  border-radius: 8px;
  background: var(--bg-card-2);
  border: 1px solid rgba(30, 39, 56, 0.65);
  font-size: 0.78rem;
}
.feat-k {
  color: var(--text-2);
}
.feat-v {
  color: var(--text);
  font-weight: 600;
  text-align: right;
  word-break: break-word;
}

@media (max-width: 1100px) {
  .replay-layout {
    grid-template-columns: 1fr;
  }
  .sidebar {
    position: static;
    max-height: 400px;
  }
  .pills-row {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .pills-row,
  .decision-grid,
  .feat-grid {
    grid-template-columns: 1fr;
  }
  .tl-row {
    grid-template-columns: 16px 74px minmax(0, 1fr);
  }
  .tl-time {
    grid-column: 3;
    text-align: left;
  }
}
</style>
