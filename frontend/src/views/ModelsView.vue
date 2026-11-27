<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Chart from 'chart.js/auto'
import { BASELINE, CART_BEHAVIOR, DATA_PREP, METRIC_COLUMNS, MODEL_ROWS, ROLE3_FUNNEL } from '@/services/reportsData'
import {
  formatInt,
  formatMetric,
  formatNumber,
  formatPct,
  formatPriceUnits,
  formatRatioPct,
  humanizeFeature,
} from '@/utils/formatters'

// Chart 1: Logistic Regression coefficients
const coefCanvas = ref(null)
let coefChart = null
const topDrivers = computed(() => BASELINE.coefficients.slice(0, 12))

// Chart 2: Price bands vs cart-vs-viewed move
const priceCanvas = ref(null)
let priceChart = null
const priceTab = ref('bands') // 'bands' | 'move'

// Chart 3: Pre-cart signal conversion explorer
const signalCanvas = ref(null)
let signalChart = null
const signalTab = ref('seconds_to_first_cart')
const SIGNAL_TABS = [
  { id: 'seconds_to_first_cart', label: 'Time to Cart' },
  { id: 'views_before_cart', label: 'Views' },
  { id: 'removes_before_cart', label: 'Removes' },
  { id: 'prior_purchase_sessions', label: 'Prior Buys' },
  { id: 'hour_utc', label: 'Hour (UTC)' },
  { id: 'weekday_utc', label: 'Weekday (UTC)' },
]

const darkTooltip = {
  backgroundColor: '#0A0E16',
  borderColor: '#2C3A52',
  borderWidth: 1,
  titleColor: '#F3F6FC',
  bodyColor: '#CBD5E1',
  padding: 10,
}

function renderCoefChart() {
  if (!coefCanvas.value) return
  if (coefChart) coefChart.destroy()
  const rows = topDrivers.value
  coefChart = new Chart(coefCanvas.value, {
    type: 'bar',
    data: {
      labels: rows.map((r) => humanizeFeature(r.feature)),
      datasets: [
        {
          label: 'Standardized log1p coefficient',
          data: rows.map((r) => r.coefficient),
          backgroundColor: rows.map((r) => (r.coefficient >= 0 ? 'rgba(59, 130, 246, 0.78)' : 'rgba(249, 115, 22, 0.78)')),
          borderColor: rows.map((r) => (r.coefficient >= 0 ? '#3B82F6' : '#F97316')),
          borderWidth: 1,
          borderRadius: 5,
        },
      ],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          ...darkTooltip,
          callbacks: {
            label(ctx) {
              const v = ctx.parsed.x
              return ` Coefficient: ${v >= 0 ? '+' : ''}${v.toFixed(4)}`
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(30, 39, 56, 0.55)' },
          ticks: { color: '#94A3B8', font: { size: 11 } },
        },
        y: {
          grid: { display: false },
          ticks: { color: '#CBD5E1', font: { size: 11 } },
        },
      },
    },
  })
}

function renderPriceChart() {
  if (!priceCanvas.value) return
  if (priceChart) priceChart.destroy()
  const isBands = priceTab.value === 'bands'
  const items = isBands ? CART_BEHAVIOR.priceBands.bands : CART_BEHAVIOR.priceBands.cart_vs_viewed_price
  const labels = items.map((d) =>
    isBands ? `${d.band} (${formatPriceUnits(d.price_min)}–${formatPriceUnits(d.price_max)})` : d.move,
  )

  priceChart = new Chart(priceCanvas.value, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Post-cart purchase rate %',
          data: items.map((d) => Number((d.purchase_rate * 100).toFixed(2))),
          backgroundColor: isBands
            ? ['rgba(59, 130, 246, 0.75)', 'rgba(217, 249, 54, 0.75)', 'rgba(34, 197, 94, 0.78)']
            : ['rgba(59, 130, 246, 0.75)', 'rgba(148, 163, 184, 0.55)', 'rgba(217, 249, 54, 0.78)'],
          borderRadius: 7,
          barPercentage: 0.58,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          ...darkTooltip,
          callbacks: {
            label(ctx) {
              const item = items[ctx.dataIndex]
              return ` Purchase rate: ${formatPct(ctx.parsed.y)} (${formatInt(item.sessions)} sessions)`
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#CBD5E1', font: { size: 11 } } },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(30, 39, 56, 0.55)' },
          ticks: { color: '#94A3B8', font: { size: 11 }, callback: (v) => `${v}%` },
        },
      },
    },
  })
}

function renderSignalChart() {
  if (!signalCanvas.value) return
  if (signalChart) signalChart.destroy()
  const items = CART_BEHAVIOR.byBucket[signalTab.value] ?? []
  signalChart = new Chart(signalCanvas.value, {
    type: 'bar',
    data: {
      labels: items.map((d) => d.bucket),
      datasets: [
        {
          label: 'Purchase rate %',
          data: items.map((d) => Number((d.purchase_rate * 100).toFixed(2))),
          backgroundColor: 'rgba(217, 249, 54, 0.72)',
          borderColor: '#D9F936',
          borderWidth: 1,
          borderRadius: 5,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          ...darkTooltip,
          callbacks: {
            label(ctx) {
              const item = items[ctx.dataIndex]
              return ` Purchase rate: ${formatPct(ctx.parsed.y)} (${formatInt(item.sessions)} sessions)`
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#CBD5E1', font: { size: 10.5 } } },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(30, 39, 56, 0.55)' },
          ticks: { color: '#94A3B8', font: { size: 11 }, callback: (v) => `${v}%` },
        },
      },
    },
  })
}

onMounted(() => {
  renderCoefChart()
  renderPriceChart()
  renderSignalChart()
})

watch(priceTab, renderPriceChart)
watch(signalTab, renderSignalChart)

onBeforeUnmount(() => {
  if (coefChart) coefChart.destroy()
  if (priceChart) priceChart.destroy()
  if (signalChart) signalChart.destroy()
})
</script>

<template>
  <div class="page models-page">
    <!-- Header -->
    <header class="m-head">
      <div>
        <h1 class="m-title">
          Models &amp; Behavior Intelligence <span class="slash" aria-hidden="true">/</span>
        </h1>
        <p class="m-sub">
          Zero-leakage purchase intent evaluation (Role 5 + Role 6) and pre-cart behavioral signals (Role 4).
        </p>
      </div>
      <span class="badge badge-blue">Primary metric: PR-AUC</span>
    </header>

    <!-- SECTION 1: Model Comparison & Pipeline Integrity (Role 5 + Role 6) -->
    <section class="sec-grid">
      <article class="card">
        <div class="card-head">
          <div>
            <h2 class="card-title">Model comparison &amp; validation benchmarks</h2>
            <p class="card-sub">
              Temporal validation on Jan 2020 ({{ formatInt(BASELINE.rows.val) }} cart sessions · no-skill PR-AUC
              {{ formatMetric(BASELINE.noSkillPrAuc) }})
            </p>
          </div>
          <span class="badge badge-lime">Selected baseline: {{ BASELINE.selectedLabel }}</span>
        </div>

        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Split</th>
                <th v-for="col in METRIC_COLUMNS" :key="col.key" class="r">{{ col.label }}</th>
                <th class="r">Threshold</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in MODEL_ROWS" :key="m.key">
                <td class="strong">
                  <div>{{ m.name }}</div>
                  <div class="sub-role">{{ m.role }}</div>
                </td>
                <td>{{ m.split }}</td>
                <template v-if="m.status === 'available' && m.metrics">
                  <td v-for="col in METRIC_COLUMNS" :key="col.key" class="r num" :class="{ strong: col.key === 'pr_auc' }">
                    {{ formatMetric(m.metrics[col.key]) }}
                  </td>
                  <td class="r num">{{ formatMetric(m.threshold) }}</td>
                </template>
                <template v-else>
                  <td colspan="6" class="r">
                    <span class="badge badge-amber">{{ m.statusLabel }}</span>
                  </td>
                </template>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Role 5 evaluated variants -->
        <div class="sub-section">
          <div class="eyebrow">Role 5 Logistic Regression Variants (Jan 2020 Validation)</div>
          <div class="table-wrap" style="margin-top: 8px">
            <table class="data-table compact">
              <thead>
                <tr>
                  <th>Variant</th>
                  <th class="r">Train PR-AUC</th>
                  <th class="r">Val PR-AUC</th>
                  <th class="r">Val ROC-AUC</th>
                  <th class="r">Best F1</th>
                  <th class="r">F1 @ 0.50</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="v in BASELINE.variants" :key="v.key">
                  <td class="strong">
                    {{ v.label }}
                    <span v-if="v.selected" class="badge badge-blue" style="margin-left: 6px">Selected</span>
                  </td>
                  <td class="r num">{{ formatMetric(v.train_pr_auc) }}</td>
                  <td class="r num strong">{{ formatMetric(v.pr_auc) }}</td>
                  <td class="r num">{{ formatMetric(v.roc_auc) }}</td>
                  <td class="r num">{{ formatMetric(v.best.f1) }}</td>
                  <td class="r num">{{ formatMetric(v.at05.f1) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </article>

      <!-- Top Predictive Drivers -->
      <article class="card">
        <div class="card-head">
          <div>
            <h2 class="card-title">Top predictive drivers (Role 5)</h2>
            <p class="card-sub">Top 12 standardized log1p coefficients by magnitude · Random Forest importances pending Role 6</p>
          </div>
        </div>
        <div class="coef-box">
          <canvas ref="coefCanvas" aria-label="Logistic regression coefficient magnitudes" />
        </div>
        <p class="note-line">
          Note: Coefficients come from <span class="mono">log1p</span>-transformed scaled features; scores are uncalibrated
          (Role 5 baseline).
        </p>
      </article>
    </section>

    <!-- Zero-Leakage Methodology + Temporal Split -->
    <section class="card">
      <div class="card-head">
        <div>
          <h2 class="card-title">Zero-leakage temporal split &amp; feature integrity</h2>
          <p class="card-sub">
            20 pre-cart &amp; first-cart features strictly bounded to <span class="mono">event_time &lt;= first_cart_time</span>
            (UTC)
          </p>
        </div>
        <span class="badge badge-green">Zero Leakage Verified</span>
      </div>

      <div class="split-grid">
        <div class="split-cards">
          <div v-for="sp in DATA_PREP.splits" :key="sp.key" class="split-card">
            <div class="sp-top">
              <span class="sp-name">{{ sp.label }}</span>
              <span class="badge">{{ sp.window }}</span>
            </div>
            <div class="sp-val num">{{ formatInt(sp.rows) }} <span class="sp-unit">cart sessions</span></div>
            <div class="sp-sub num">
              {{ formatInt(sp.positives) }} purchases · {{ formatPct(sp.positive_rate_pct) }} positive rate
            </div>
          </div>
        </div>

        <ul class="rules-list">
          <li v-for="(rule, i) in DATA_PREP.rules" :key="i">{{ rule }}</li>
        </ul>
      </div>
    </section>

    <!-- SECTION 2: Cart Behavior & Catalog Intelligence (Role 4 — Real Data) -->
    <section class="card">
      <div class="card-head">
        <div>
          <h2 class="card-title">Cart behavior &amp; catalog intelligence (Role 4)</h2>
          <p class="card-sub">
            {{ formatInt(CART_BEHAVIOR.meta.n_sessions) }} sessions across {{ formatInt(CART_BEHAVIOR.meta.n_users) }} users
            ({{ formatRatioPct(CART_BEHAVIOR.meta.overall_purchase_rate) }} baseline conversion)
          </p>
        </div>
        <span class="badge badge-amber">Descriptive analysis on intent_train only</span>
      </div>

      <div class="charts-two">
        <!-- Price Bands / Cart vs Viewed -->
        <div class="sub-panel">
          <div class="sub-head">
            <div>
              <h3 class="sub-title">Price sensitivity at first cart</h3>
              <p class="card-sub">Recorded price units (no currency assumed)</p>
            </div>
            <div class="segmented small">
              <button type="button" :class="{ active: priceTab === 'bands' }" @click="priceTab = 'bands'">
                Price Bands
              </button>
              <button type="button" :class="{ active: priceTab === 'move' }" @click="priceTab = 'move'">
                Cart vs Viewed
              </button>
            </div>
          </div>
          <div class="bar-box">
            <canvas ref="priceCanvas" aria-label="Price band purchase conversion chart" />
          </div>
        </div>

        <!-- Pre-cart Signals -->
        <div class="sub-panel">
          <div class="sub-head">
            <div>
              <h3 class="sub-title">Conversion by pre-cart signal</h3>
              <p class="card-sub">Post-cart purchase rate across behavioral buckets</p>
            </div>
            <div class="segmented small wrap-seg">
              <button
                v-for="t in SIGNAL_TABS"
                :key="t.id"
                type="button"
                :class="{ active: signalTab === t.id }"
                @click="signalTab = t.id"
              >
                {{ t.label }}
              </button>
            </div>
          </div>
          <div class="bar-box">
            <canvas ref="signalCanvas" aria-label="Pre-cart behavioral conversion chart" />
          </div>
        </div>
      </div>

      <!-- Buyer vs Non-Buyer Table + Brand/Catalog summary -->
      <div class="role4-bottom">
        <div class="sub-panel">
          <h3 class="sub-title" style="margin-bottom: 10px">Buyer vs non-buyer pre-cart behavior (intent_train)</h3>
          <div class="table-wrap">
            <table class="data-table compact">
              <thead>
                <tr>
                  <th>Feature</th>
                  <th class="r">Buyer Mean</th>
                  <th class="r">Non-Buyer Mean</th>
                  <th class="r">Buyer Median</th>
                  <th class="r">Non-Buyer Median</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in CART_BEHAVIOR.numeric" :key="row.feature">
                  <td class="strong">{{ humanizeFeature(row.feature) }}</td>
                  <td class="r num">{{ formatNumber(row.buyer_mean) }}</td>
                  <td class="r num">{{ formatNumber(row.non_buyer_mean) }}</td>
                  <td class="r num">{{ formatNumber(row.buyer_median, 1) }}</td>
                  <td class="r num">{{ formatNumber(row.non_buyer_median, 1) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="catalog-side">
          <div class="sub-panel">
            <h3 class="sub-title">Brand presence effect</h3>
            <p class="card-sub" style="margin-bottom: 10px">Brand presence at first cart &amp; pre-cart brand breadth</p>
            <div class="mini-kv-list">
              <div v-for="b in CART_BEHAVIOR.brand.cart_item_has_brand" :key="b.bucket" class="mini-kv">
                <span>Cart item: {{ b.bucket }}</span>
                <span class="num">
                  <strong>{{ formatRatioPct(b.purchase_rate) }}</strong>
                  <span class="muted"> ({{ formatInt(b.sessions) }})</span>
                </span>
              </div>
              <div v-for="b in CART_BEHAVIOR.brand.distinct_brands_viewed_before_cart" :key="b.bucket" class="mini-kv">
                <span>Pre-cart distinct brands: {{ b.bucket }}</span>
                <span class="num">
                  <strong>{{ formatRatioPct(b.purchase_rate) }}</strong>
                  <span class="muted"> ({{ formatInt(b.sessions) }})</span>
                </span>
              </div>
            </div>
          </div>

          <div class="sub-panel">
            <h3 class="sub-title">Catalog concentration (train)</h3>
            <div class="mini-kv-list" style="margin-top: 8px">
              <div class="mini-kv">
                <span>Distinct categories</span>
                <strong class="num">{{ formatInt(CART_BEHAVIOR.catalog.n_categories) }}</strong>
              </div>
              <div class="mini-kv">
                <span>Distinct products</span>
                <strong class="num">{{ formatInt(CART_BEHAVIOR.catalog.n_products) }}</strong>
              </div>
              <div class="mini-kv">
                <span>Top 10 categories share</span>
                <strong class="num">{{ formatRatioPct(CART_BEHAVIOR.catalog.top10_categories_share_of_sessions) }}</strong>
              </div>
              <div class="mini-kv">
                <span>Top 50 products share</span>
                <strong class="num">{{ formatRatioPct(CART_BEHAVIOR.catalog.top50_products_share_of_sessions) }}</strong>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- SECTION 3: Role 3 Funnel & Data Quality Slot -->
    <section class="card callout pending role3-card">
      <div class="r3-body">
        <div class="r3-head">
          <div>
            <h2 class="card-title">Funnel &amp; data quality summary (Role 3)</h2>
            <p class="card-sub">Expected source: <span class="mono">{{ ROLE3_FUNNEL.expectedPath }}</span></p>
          </div>
          <span class="badge badge-amber">{{ ROLE3_FUNNEL.statusLabel }}</span>
        </div>
        <p class="r3-copy">
          Role 3's detailed monthly EDA breakdown will bind here automatically once merged. Verified global dataset prep
          baselines (<span class="mono">dataset_prep_summary.json</span>):
          <strong class="num">{{ formatInt(DATA_PREP.overall.total_valid_sessions) }}</strong> valid sessions,
          <strong class="num">{{ formatInt(DATA_PREP.overall.sessions_with_cart_without_purchase) }}</strong> abandoned
          cart sessions, and
          <strong class="num">{{ formatPriceUnits(DATA_PREP.overall.total_recorded_purchase_pos_only) }}</strong>
          positive-only recorded purchase price units (no currency assumed).
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.models-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.m-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}
.m-title {
  font-size: clamp(1.6rem, 2.4vw, 2.1rem);
  font-weight: 700;
  letter-spacing: -0.025em;
}
.slash {
  color: var(--text-3);
  font-weight: 300;
}
.m-sub {
  font-size: 0.88rem;
  color: var(--text-2);
  margin-top: 4px;
}

.sec-grid {
  display: grid;
  grid-template-columns: 1.18fr 1fr;
  gap: 16px;
}

.sub-role {
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--text-3);
  margin-top: 2px;
}

.sub-section {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.data-table.compact th,
.data-table.compact td {
  padding: 7px 9px;
  font-size: 0.78rem;
}

.coef-box {
  height: 310px;
  position: relative;
}
.note-line {
  margin-top: 10px;
  font-size: 0.74rem;
  color: var(--text-3);
}

/* Split grid */
.split-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
  align-items: start;
}
.split-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.split-card {
  padding: 12px 13px;
  border-radius: 11px;
  border: 1px solid var(--border);
  background: var(--bg-card-2);
}
.sp-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.sp-name {
  font-weight: 700;
  font-size: 0.86rem;
}
.sp-val {
  font-size: 1.2rem;
  font-weight: 700;
  margin-top: 8px;
}
.sp-unit {
  font-size: 0.74rem;
  font-weight: 500;
  color: var(--text-2);
}
.sp-sub {
  font-size: 0.73rem;
  color: var(--text-3);
  margin-top: 3px;
}

.rules-list {
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.79rem;
  color: var(--text-2);
}

/* Role 4 */
.charts-two {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.sub-panel {
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--bg-card-2);
}
.sub-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.sub-title {
  font-size: 0.9rem;
  font-weight: 650;
}
.wrap-seg {
  flex-wrap: wrap;
}
.bar-box {
  height: 220px;
  position: relative;
}

.role4-bottom {
  display: grid;
  grid-template-columns: 1.35fr 1fr;
  gap: 14px;
  margin-top: 14px;
}
.catalog-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.mini-kv-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.mini-kv {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  font-size: 0.79rem;
  color: var(--text-2);
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(30, 39, 56, 0.65);
}
.mini-kv:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.mini-kv strong {
  color: var(--text);
}

/* Role 3 pending */
.role3-card {
  padding: 20px;
}
.r3-body {
  width: 100%;
}
.r3-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.r3-copy {
  font-size: 0.82rem;
  color: var(--text-2);
}

@media (max-width: 1120px) {
  .sec-grid,
  .split-grid,
  .charts-two,
  .role4-bottom {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .split-cards {
    grid-template-columns: 1fr;
  }
}
</style>
