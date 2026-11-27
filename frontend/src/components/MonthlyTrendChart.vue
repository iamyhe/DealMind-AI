<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Chart from 'chart.js/auto'
import { formatInt, formatPct } from '@/utils/formatters'

const props = defineProps({
  monthly: { type: Array, required: true },
  metricMode: { type: String, default: 'rates' }, // 'rates' | 'volumes'
  activePeriod: { type: String, default: 'ALL' },
})

const canvasEl = ref(null)
let chart = null

const MONTH_NAMES = {
  '2019-10': 'Oct',
  '2019-11': 'Nov',
  '2019-12': 'Dec',
  '2020-01': 'Jan',
  '2020-02': 'Feb',
}

function buildConfig() {
  const labels = props.monthly.map((m) => MONTH_NAMES[m.period] || m.period)
  const isRates = props.metricMode === 'rates'

  const pointRadius = (periodList) => periodList.map((m) => (m.period === props.activePeriod ? 6.5 : 4))

  const datasets = isRates
    ? [
        {
          label: 'Cart Abandonment %',
          data: props.monthly.map((m) => m.session_cart_abandonment_rate_pct),
          borderColor: '#3B82F6',
          backgroundColor: 'rgba(59, 130, 246, 0.14)',
          pointBackgroundColor: '#3B82F6',
          pointBorderColor: '#070A0F',
          pointBorderWidth: 1.5,
          pointRadius: pointRadius(props.monthly),
          borderWidth: 2.2,
          tension: 0.32,
        },
        {
          label: 'Overall Purchase Rate %',
          data: props.monthly.map((m) => m.overall_purchase_rate_pct),
          borderColor: '#D9F936',
          backgroundColor: 'rgba(217, 249, 54, 0.12)',
          pointBackgroundColor: '#D9F936',
          pointBorderColor: '#070A0F',
          pointBorderWidth: 1.5,
          pointRadius: pointRadius(props.monthly),
          borderWidth: 2.2,
          tension: 0.32,
        },
        {
          label: 'View → Purchase %',
          data: props.monthly.map((m) => m.view_to_purchase_rate_pct),
          borderColor: '#F97316',
          backgroundColor: 'rgba(249, 115, 22, 0.12)',
          pointBackgroundColor: '#F97316',
          pointBorderColor: '#070A0F',
          pointBorderWidth: 1.5,
          pointRadius: pointRadius(props.monthly),
          borderWidth: 2.2,
          tension: 0.32,
        },
      ]
    : [
        {
          label: 'Valid Sessions',
          data: props.monthly.map((m) => m.total_valid_sessions),
          borderColor: '#3B82F6',
          backgroundColor: 'rgba(59, 130, 246, 0.12)',
          pointBackgroundColor: '#3B82F6',
          pointBorderColor: '#070A0F',
          pointBorderWidth: 1.5,
          pointRadius: pointRadius(props.monthly),
          borderWidth: 2.2,
          tension: 0.32,
        },
        {
          label: 'Cart Sessions',
          data: props.monthly.map((m) => m.sessions_with_cart),
          borderColor: '#D9F936',
          backgroundColor: 'rgba(217, 249, 54, 0.1)',
          pointBackgroundColor: '#D9F936',
          pointBorderColor: '#070A0F',
          pointBorderWidth: 1.5,
          pointRadius: pointRadius(props.monthly),
          borderWidth: 2.2,
          tension: 0.32,
        },
        {
          label: 'Purchase Sessions',
          data: props.monthly.map((m) => m.sessions_with_purchase),
          borderColor: '#F97316',
          backgroundColor: 'rgba(249, 115, 22, 0.12)',
          pointBackgroundColor: '#F97316',
          pointBorderColor: '#070A0F',
          pointBorderWidth: 1.5,
          pointRadius: pointRadius(props.monthly),
          borderWidth: 2.2,
          tension: 0.32,
        },
      ]

  return {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'right',
          labels: {
            color: '#94A3B8',
            usePointStyle: true,
            pointStyle: 'circle',
            boxWidth: 7,
            boxHeight: 7,
            padding: 14,
            font: { size: 11.5, family: 'Inter Variable, Inter, sans-serif' },
          },
        },
        tooltip: {
          backgroundColor: '#0A0E16',
          borderColor: '#2C3A52',
          borderWidth: 1,
          titleColor: '#F3F6FC',
          bodyColor: '#CBD5E1',
          padding: 10,
          callbacks: {
            title(items) {
              const i = items?.[0]?.dataIndex ?? 0
              return `${props.monthly[i]?.period ?? ''} (UTC)`
            },
            label(ctx) {
              const val = ctx.parsed.y
              return ` ${ctx.dataset.label}: ${isRates ? formatPct(val) : formatInt(val)}`
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
          min: 0,
          max: isRates ? 100 : undefined,
          grid: { color: 'rgba(30, 39, 56, 0.55)' },
          ticks: {
            color: '#94A3B8',
            font: { size: 11 },
            callback(v) {
              if (isRates) return `${v}%`
              return v >= 1000 ? `${Math.round(v / 1000)}k` : v
            },
          },
        },
      },
    },
  }
}

function renderChart() {
  if (!canvasEl.value || !props.monthly.length) return
  if (chart) chart.destroy()
  chart = new Chart(canvasEl.value, buildConfig())
}

onMounted(renderChart)
watch(() => [props.monthly, props.metricMode, props.activePeriod], renderChart, { deep: true })
onBeforeUnmount(() => {
  if (chart) {
    chart.destroy()
    chart = null
  }
})
</script>

<template>
  <div class="chart-box">
    <canvas ref="canvasEl" aria-label="Monthly basket trend chart" />
  </div>
</template>

<style scoped>
.chart-box {
  position: relative;
  height: 215px;
  width: 100%;
}
</style>
