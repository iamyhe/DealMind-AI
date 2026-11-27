<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import BasketFunnelSvg from '@/components/BasketFunnelSvg.vue'
import MonthlyTrendChart from '@/components/MonthlyTrendChart.vue'
import StateError from '@/components/StateError.vue'
import StateLoading from '@/components/StateLoading.vue'
import { getMonthlySummaries, getSummary } from '@/services/api'
import { settings } from '@/services/config'
import { METRIC_COLUMNS, MODEL_ROWS } from '@/services/reportsData'
import { formatInt, formatMetric, formatPct, formatPriceUnits } from '@/utils/formatters'

const PERIOD_OPTIONS = [
  { id: 'ALL', label: 'ALL', full: 'Oct 2019 – Feb 2020' },
  { id: '2019-10', label: 'Oct', full: 'October 2019' },
  { id: '2019-11', label: 'Nov', full: 'November 2019' },
  { id: '2019-12', label: 'Dec', full: 'December 2019' },
  { id: '2020-01', label: 'Jan', full: 'January 2020' },
  { id: '2020-02', label: 'Feb', full: 'February 2020' },
]

const activePeriod = ref('ALL')
const summary = ref(null)
const monthly = ref([])
const loading = ref(true)
const switching = ref(false)
const error = ref(null)
const chartMode = ref('rates') // 'rates' | 'volumes'

const activeOption = computed(() => PERIOD_OPTIONS.find((p) => p.id === activePeriod.value) ?? PERIOD_OPTIONS[0])

async function loadAll(initial = false) {
  if (initial) loading.value = true
  else switching.value = true
  error.value = null
  try {
    const [sum, months] = await Promise.all([getSummary(activePeriod.value), getMonthlySummaries()])
    summary.value = sum
    monthly.value = months
  } catch (e) {
    error.value = e?.message || 'Failed to load summary metrics'
  } finally {
    loading.value = false
    switching.value = false
  }
}

async function selectPeriod(period) {
  if (period === activePeriod.value && summary.value) return
  activePeriod.value = period
  switching.value = true
  error.value = null
  try {
    summary.value = await getSummary(period)
  } catch (e) {
    error.value = e?.message || 'Failed to load period metrics'
  } finally {
    switching.value = false
  }
}

onMounted(() => loadAll(true))
watch(
  () => settings.dataVersion,
  () => loadAll(!summary.value),
)
</script>

<template>
  <div class="page dash-page">
    <!-- Top Header + Period Selector -->
    <header class="dash-head">
      <div>
        <h1 class="hero-title">
          Basket Intelligence <span class="slash" aria-hidden="true">/</span>
        </h1>
        <p class="hero-sub">Historical commerce signals · {{ activeOption.full }} (UTC)</p>
      </div>

      <div class="period-wrap">
        <span class="period-label">Period</span>
        <div class="segmented" role="group" aria-label="Filter summary period">
          <button
            v-for="p in PERIOD_OPTIONS"
            :key="p.id"
            type="button"
            :class="{ active: activePeriod === p.id }"
            :aria-pressed="activePeriod === p.id"
            @click="selectPeriod(p.id)"
          >
            {{ p.label }}
          </button>
        </div>
      </div>
    </header>

    <StateLoading v-if="loading" variant="dashboard" />
    <StateError v-else-if="error && !summary" :message="error" @retry="loadAll(true)" />

    <template v-else-if="summary">
      <StateError v-if="error" :message="error" @retry="selectPeriod(activePeriod)" />

      <!-- 5 KPI Cards Row -->
      <section class="kpi-grid" :class="{ refreshing: switching }" aria-label="Key funnel indicators">
        <article class="card kpi-card">
          <div class="kpi-icon kpi-blue" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M8 9 L10 4 H14 L16 9" stroke-linecap="round" stroke-linejoin="round" />
              <path d="M3 9 H21 L19 19 Q18.5 20.5 17 20.5 H7 Q5.5 20.5 5 19 Z" stroke-linejoin="round" />
              <path d="M4 13.5 H20 M9 9 L9.8 20.5 M15 9 L14.2 20.5" stroke-opacity="0.65" />
            </svg>
          </div>
          <div class="kpi-val num">{{ formatInt(summary.total_valid_sessions) }}</div>
          <div class="kpi-label">Valid Sessions</div>
          <div class="kpi-sub num">With View: {{ formatInt(summary.sessions_with_view) }}</div>
        </article>

        <article class="card kpi-card">
          <div class="kpi-icon kpi-orange" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M21 12a9 9 0 1 1-2.64-6.36" stroke-linecap="round" />
              <path d="M21 3v6h-6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </div>
          <div class="kpi-val num">{{ formatPct(summary.session_cart_abandonment_rate_pct) }}</div>
          <div class="kpi-label">Cart Abandonment</div>
          <div class="kpi-sub num">Cart Sessions: {{ formatInt(summary.sessions_with_cart) }}</div>
        </article>

        <article class="card kpi-card">
          <div class="kpi-icon kpi-lime" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8">
              <circle cx="9" cy="20" r="1.4" />
              <circle cx="17" cy="20" r="1.4" />
              <path d="M3 4h2.5l2.1 10.5a1.5 1.5 0 0 0 1.47 1.2h8.1a1.5 1.5 0 0 0 1.45-1.12L20.5 8H6.3" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </div>
          <div class="kpi-val num">{{ formatPct(summary.overall_purchase_rate_pct) }}</div>
          <div class="kpi-label">Overall Purchase Rate</div>
          <div class="kpi-sub num">Purchase Sessions: {{ formatInt(summary.sessions_with_purchase) }}</div>
        </article>

        <article class="card kpi-card">
          <div class="kpi-icon kpi-blue" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.9">
              <path d="M5 12h14M13 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </div>
          <div class="kpi-val num">{{ formatPct(summary.view_to_purchase_rate_pct) }}</div>
          <div class="kpi-label">View → Purchase</div>
          <div class="kpi-sub">View-to-purchase sessions</div>
        </article>

        <article class="card kpi-card">
          <div class="kpi-icon kpi-lime" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8">
              <ellipse cx="12" cy="7" rx="7" ry="2.6" />
              <path d="M5 7v5c0 1.44 3.13 2.6 7 2.6s7-1.16 7-2.6V7" />
              <path d="M5 12v5c0 1.44 3.13 2.6 7 2.6s7-1.16 7-2.6v-5" />
            </svg>
          </div>
          <div class="kpi-val num">{{ formatPriceUnits(summary.historical_aov_pos) }}</div>
          <div class="kpi-label">Recorded Price Units (AOV)</div>
          <div class="kpi-sub num">Signed AOV: {{ formatPriceUnits(summary.historical_aov_signed) }} · No currency</div>
        </article>
      </section>

      <!-- Centerpiece: Wireframe Basket Funnel -->
      <section class="card funnel-card" :class="{ refreshing: switching }">
        <BasketFunnelSvg :summary="summary" />
        <div class="funnel-footnote">
          <span class="info-pill" aria-hidden="true">i</span>
          <span>
            Historical data: {{ activeOption.full }}, UTC. Recorded source price units only — no currency assumed.
          </span>
        </div>
      </section>

      <!-- Bottom Two-Column Row -->
      <section class="bottom-grid">
        <article class="card trend-card">
          <div class="card-head">
            <div>
              <h2 class="card-title">Monthly trend</h2>
              <p class="card-sub">Key basket signals by month (Oct 2019 – Feb 2020)</p>
            </div>
            <div class="segmented small" role="group" aria-label="Chart metric mode">
              <button type="button" :class="{ active: chartMode === 'rates' }" @click="chartMode = 'rates'">
                Rates (%)
              </button>
              <button type="button" :class="{ active: chartMode === 'volumes' }" @click="chartMode = 'volumes'">
                Session Volumes
              </button>
            </div>
          </div>
          <MonthlyTrendChart :monthly="monthly" :metric-mode="chartMode" :active-period="activePeriod" />
        </article>

        <article class="card model-card">
          <div class="card-head">
            <div>
              <h2 class="card-title">Model score comparison</h2>
              <p class="card-sub">Validation evaluation (Jan 2020) vs final test candidate</p>
            </div>
            <span class="badge badge-blue">PR-AUC primary</span>
          </div>

          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th v-for="col in METRIC_COLUMNS" :key="col.key" class="r">{{ col.label }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in MODEL_ROWS" :key="m.key">
                  <td class="strong">
                    <div>{{ m.name }}</div>
                    <div class="model-role">{{ m.role }}</div>
                  </td>
                  <template v-if="m.status === 'available' && m.metrics">
                    <td v-for="col in METRIC_COLUMNS" :key="col.key" class="r num" :class="{ strong: col.key === 'pr_auc' }">
                      {{ formatMetric(m.metrics[col.key]) }}
                    </td>
                  </template>
                  <template v-else>
                    <td v-for="(col, i) in METRIC_COLUMNS" :key="col.key" class="r">
                      <span v-if="i === 0" class="badge badge-amber">Pending merge</span>
                      <span v-else class="muted">—</span>
                    </td>
                  </template>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="model-foot">
            <RouterLink to="/models" class="link-arrow">
              View full model &amp; cart behavior analysis <span aria-hidden="true">→</span>
            </RouterLink>
          </div>
        </article>
      </section>

      <!-- Bottom CTA Banner -->
      <section class="cta-banner card">
        <div class="cta-copy">
          <span class="badge badge-lime">Feb 2020 · Test Split</span>
          <span>Inspect real February 2020 cart sessions step-by-step before revealing outcomes.</span>
        </div>
        <RouterLink to="/replay" class="btn btn-lime">
          Open Session Replay <span aria-hidden="true">→</span>
        </RouterLink>
      </section>
    </template>
  </div>
</template>

<style scoped>
.dash-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.dash-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.hero-title {
  font-size: clamp(1.65rem, 2.5vw, 2.2rem);
  font-weight: 700;
  letter-spacing: -0.028em;
  line-height: 1.15;
}
.slash {
  color: var(--text-3);
  font-weight: 300;
}
.hero-sub {
  font-size: 0.9rem;
  color: var(--text-2);
  margin-top: 4px;
}

.period-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
}
.period-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-3);
}

/* KPI Row */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
  transition: opacity 0.18s ease;
}
.refreshing {
  opacity: 0.72;
}

.kpi-card {
  padding: 18px 18px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.kpi-icon {
  width: 30px;
  height: 28px;
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}
.kpi-blue {
  color: var(--browse-2);
}
.kpi-orange {
  color: var(--outcome);
}
.kpi-lime {
  color: var(--cart);
}
.kpi-val {
  font-size: clamp(1.45rem, 1.85vw, 1.82rem);
  font-weight: 700;
  letter-spacing: -0.025em;
  line-height: 1.15;
  color: var(--text);
}
.kpi-label {
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--text-2);
  margin-top: 3px;
}
.kpi-sub {
  font-size: 0.73rem;
  color: var(--text-3);
  margin-top: 2px;
}

/* Funnel Card */
.funnel-card {
  padding: 22px 24px 16px;
  transition: opacity 0.18s ease, border-color 0.2s ease;
}
.funnel-footnote {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  font-size: 0.76rem;
  color: var(--text-3);
}
.info-pill {
  width: 16px;
  height: 16px;
  border-radius: 999px;
  border: 1px solid var(--text-3);
  font-size: 0.66rem;
  font-weight: 700;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

/* Bottom Grid */
.bottom-grid {
  display: grid;
  grid-template-columns: 1.25fr 1fr;
  gap: 16px;
}
.model-card {
  display: flex;
  flex-direction: column;
}
.model-role {
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--text-3);
  margin-top: 2px;
}
.model-foot {
  margin-top: auto;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

/* Bottom CTA Banner */
.cta-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 15px 20px;
  background: linear-gradient(90deg, rgba(37, 99, 235, 0.08), rgba(217, 249, 54, 0.06));
  flex-wrap: wrap;
}
.cta-copy {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.88rem;
  color: var(--text-2);
  flex-wrap: wrap;
}

@media (max-width: 1180px) {
  .kpi-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .bottom-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .period-wrap {
    align-items: flex-start;
  }
  .segmented {
    flex-wrap: wrap;
  }
}

@media (max-width: 480px) {
  .kpi-grid {
    grid-template-columns: 1fr;
  }
}
</style>
