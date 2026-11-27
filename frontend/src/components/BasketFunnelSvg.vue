<script setup>
import { computed, ref, useId } from 'vue'
import { formatInt, formatPct } from '@/utils/formatters'

const props = defineProps({
  summary: { type: Object, required: true },
})

const uid = useId()
const hovered = ref(null)

const metrics = computed(() => {
  const s = props.summary || {}
  const valid = Number(s.total_valid_sessions) || 0
  const view = Number(s.sessions_with_view) || 0
  const cart = Number(s.sessions_with_cart) || 0
  const purchase = Number(s.sessions_with_purchase) || 0

  const pct = (n, d) => (d > 0 ? (n / d) * 100 : 0)
  const viewShare = pct(view, valid)
  const cartShare = pct(cart, valid)
  const viewToCart = pct(cart, view)
  const cartAbandon = Number(s.session_cart_abandonment_rate_pct ?? 0)
  const cartRetain = Math.max(0, 100 - cartAbandon)

  return {
    valid,
    view,
    cart,
    purchase,
    viewShare,
    cartShare,
    viewToCart,
    cartAbandon,
    cartRetain,
    overallPurchase: Number(s.overall_purchase_rate_pct ?? pct(purchase, valid)),
    viewToPurchase: Number(s.view_to_purchase_rate_pct ?? 0),
  }
})

// Generate horizontal + perspective vertical basket ribs once for the 680x260 viewBox
const hRibs = [84, 106, 128, 150, 172, 194, 216]
const vRibs = Array.from({ length: 17 }, (_, i) => {
  const t = i / 16
  const xTop = 44 + t * 592
  const xBot = 92 + t * 496
  return { xTop, xBot }
})

const zones = computed(() => [
  {
    id: 'browse',
    label: 'BROWSE',
    title: 'Sessions with View',
    count: metrics.value.view,
    sub: `${formatPct(metrics.value.viewShare, 1)} of valid`,
    detail: `${formatInt(metrics.value.view)} of ${formatInt(metrics.value.valid)} valid sessions recorded ≥1 product view.`,
    color: '#3B82F6',
    cx: 158,
    cy: 178,
  },
  {
    id: 'cart',
    label: 'CART',
    title: 'Sessions with Cart',
    count: metrics.value.cart,
    sub: `${formatPct(metrics.value.cartShare, 1)} of valid`,
    detail: `${formatPct(metrics.value.viewToCart, 1)} relative to viewed sessions (${formatPct(metrics.value.cartAbandon)} abandoned).`,
    color: '#D9F936',
    cx: 356,
    cy: 192,
  },
  {
    id: 'outcome',
    label: 'OUTCOME',
    title: 'Purchase Sessions',
    count: metrics.value.purchase,
    sub: `${formatPct(metrics.value.overallPurchase, 2)} of valid`,
    detail: `Overall conversion ${formatPct(metrics.value.overallPurchase)} · View→Purchase ${formatPct(metrics.value.viewToPurchase)}.`,
    color: '#F97316',
    cx: 536,
    cy: 205,
  },
])

const nodes = computed(() => [
  { x: 96, y: 174, r: 4.5, c: '#3B82F6', zone: zones.value[0] },
  { x: 158, y: 180, r: 6.5, c: '#3B82F6', zone: zones.value[0], main: true },
  { x: 224, y: 172, r: 4.5, c: '#60A5FA', zone: zones.value[0] },
  { x: 294, y: 184, r: 4.5, c: '#A3E635', zone: zones.value[1] },
  { x: 356, y: 193, r: 6.5, c: '#D9F936', zone: zones.value[1], main: true },
  { x: 422, y: 204, r: 4.5, c: '#EAB308', zone: zones.value[1] },
  { x: 492, y: 203, r: 4.5, c: '#FB923C', zone: zones.value[2] },
  { x: 548, y: 206, r: 6.5, c: '#F97316', zone: zones.value[2], main: true },
])

const activeZone = computed(() => zones.value.find((z) => z.id === hovered.value) || null)
</script>

<template>
  <div class="funnel-layout">
    <div class="basket-stage">
      <svg
        class="basket-svg"
        viewBox="0 0 680 264"
        role="img"
        :aria-label="`Historical basket funnel: ${formatInt(metrics.view)} browse sessions, ${formatInt(metrics.cart)} cart sessions, ${formatInt(metrics.purchase)} purchase sessions.`"
      >
        <defs>
          <!-- Outer basket silhouette clip -->
          <clipPath :id="`${uid}-shell`">
            <path d="M 32 68 L 648 68 L 598 228 Q 593 242 576 242 L 104 242 Q 87 242 82 228 Z" />
          </clipPath>
          <clipPath :id="`${uid}-z1`">
            <rect x="0" y="50" width="256" height="210" />
          </clipPath>
          <clipPath :id="`${uid}-z2`">
            <rect x="256" y="50" width="192" height="210" />
          </clipPath>
          <clipPath :id="`${uid}-z3`">
            <rect x="448" y="50" width="232" height="210" />
          </clipPath>

          <!-- Curve gradient across the 3 phases -->
          <linearGradient :id="`${uid}-curve`" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#3B82F6" />
            <stop offset="48%" stop-color="#D9F936" />
            <stop offset="100%" stop-color="#F97316" />
          </linearGradient>

          <!-- Ambient interior fills -->
          <linearGradient :id="`${uid}-bg-z1`" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#2563EB" stop-opacity="0.16" />
            <stop offset="100%" stop-color="#2563EB" stop-opacity="0.03" />
          </linearGradient>
          <linearGradient :id="`${uid}-bg-z2`" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#D9F936" stop-opacity="0.14" />
            <stop offset="100%" stop-color="#D9F936" stop-opacity="0.02" />
          </linearGradient>
          <linearGradient :id="`${uid}-bg-z3`" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stop-color="#F97316" stop-opacity="0.16" />
            <stop offset="100%" stop-color="#F97316" stop-opacity="0.03" />
          </linearGradient>

          <filter :id="`${uid}-glow`" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3.2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <!-- Back rim & top handle (3D perspective) -->
        <path
          d="M 228 62 L 260 15 Q 264 10 272 10 L 408 10 Q 416 10 420 15 L 452 62"
          fill="none"
          stroke="#475569"
          stroke-width="10"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <path
          d="M 232 62 L 263 17 Q 266 13 273 13 L 407 13 Q 414 13 417 17 L 448 62"
          fill="none"
          stroke="#94A3B8"
          stroke-opacity="0.38"
          stroke-width="2"
          stroke-linecap="round"
        />
        <!-- Recessed back rim -->
        <path
          d="M 46 62 Q 340 50 634 62"
          fill="none"
          stroke="#334155"
          stroke-width="2"
          stroke-opacity="0.7"
        />

        <!-- Interior clipped zone washes + wireframe mesh -->
        <g :clip-path="`url(#${uid}-shell)`">
          <rect x="0" y="58" width="256" height="190" :fill="`url(#${uid}-bg-z1)`" />
          <rect x="256" y="58" width="192" height="190" :fill="`url(#${uid}-bg-z2)`" />
          <rect x="448" y="58" width="232" height="190" :fill="`url(#${uid}-bg-z3)`" />

          <!-- Zone 1: BROWSE mesh (Blue) -->
          <g :clip-path="`url(#${uid}-z1)`" :opacity="hovered && hovered !== 'browse' ? 0.45 : 0.92">
            <line
              v-for="y in hRibs"
              :key="`z1h-${y}`"
              x1="28"
              :y1="y"
              x2="652"
              :y2="y"
              stroke="#3B82F6"
              stroke-opacity="0.28"
              stroke-width="1.05"
            />
            <line
              v-for="(r, idx) in vRibs"
              :key="`z1v-${idx}`"
              :x1="r.xTop"
              y1="66"
              :x2="r.xBot"
              y2="244"
              stroke="#3B82F6"
              stroke-opacity="0.32"
              stroke-width="1.05"
            />
          </g>

          <!-- Zone 2: CART mesh (Acid Lime) -->
          <g :clip-path="`url(#${uid}-z2)`" :opacity="hovered && hovered !== 'cart' ? 0.45 : 0.92">
            <line
              v-for="y in hRibs"
              :key="`z2h-${y}`"
              x1="28"
              :y1="y"
              x2="652"
              :y2="y"
              stroke="#D9F936"
              stroke-opacity="0.28"
              stroke-width="1.05"
            />
            <line
              v-for="(r, idx) in vRibs"
              :key="`z2v-${idx}`"
              :x1="r.xTop"
              y1="66"
              :x2="r.xBot"
              y2="244"
              stroke="#D9F936"
              stroke-opacity="0.32"
              stroke-width="1.05"
            />
          </g>

          <!-- Zone 3: OUTCOME mesh (Vivid Orange) -->
          <g :clip-path="`url(#${uid}-z3)`" :opacity="hovered && hovered !== 'outcome' ? 0.45 : 0.92">
            <line
              v-for="y in hRibs"
              :key="`z3h-${y}`"
              x1="28"
              :y1="y"
              x2="652"
              :y2="y"
              stroke="#F97316"
              stroke-opacity="0.3"
              stroke-width="1.05"
            />
            <line
              v-for="(r, idx) in vRibs"
              :key="`z3v-${idx}`"
              :x1="r.xTop"
              y1="66"
              :x2="r.xBot"
              y2="244"
              stroke="#F97316"
              stroke-opacity="0.34"
              stroke-width="1.05"
            />
          </g>

          <!-- Zone boundary dividers -->
          <line x1="256" y1="68" x2="256" y2="242" stroke="#D9F936" stroke-opacity="0.45" stroke-width="1.4" />
          <line x1="448" y1="68" x2="448" y2="242" stroke="#F97316" stroke-opacity="0.55" stroke-width="1.4" />

          <!-- Subtle area glow under the funnel curve -->
          <path
            d="M 88 174 C 145 186, 185 170, 232 173 C 285 177, 330 190, 382 197 C 436 205, 494 205, 558 206 L 558 242 L 88 242 Z"
            :fill="`url(#${uid}-curve)`"
            fill-opacity="0.09"
          />

          <!-- Glowing funnel curve -->
          <path
            d="M 88 174 C 145 186, 185 170, 232 173 C 285 177, 330 190, 382 197 C 436 205, 494 205, 558 206"
            fill="none"
            :stroke="`url(#${uid}-curve)`"
            stroke-width="2.6"
            stroke-linecap="round"
            :filter="`url(#${uid}-glow)`"
          />

          <!-- Curve nodes -->
          <g v-for="(n, idx) in nodes" :key="idx">
            <circle
              v-if="n.main"
              :cx="n.x"
              :cy="n.y"
              r="11"
              :fill="n.c"
              fill-opacity="0.18"
            />
            <circle
              :cx="n.x"
              :cy="n.y"
              :r="hovered === n.zone.id && n.main ? n.r + 1.8 : n.r"
              :fill="n.c"
              stroke="#070A0F"
              stroke-width="1.5"
              class="node-dot"
            />
          </g>
        </g>

        <!-- Basket outer neon rim strokes per zone -->
        <path
          d="M 256 68 L 36 68 Q 28 68 32 78 L 82 228 Q 87 242 104 242 L 256 242"
          fill="none"
          stroke="#3B82F6"
          stroke-width="2.2"
          stroke-linejoin="round"
        />
        <path d="M 256 68 L 448 68 M 256 242 L 448 242" fill="none" stroke="#D9F936" stroke-width="2.2" />
        <path
          d="M 448 68 L 644 68 Q 652 68 648 78 L 598 228 Q 593 242 576 242 L 448 242"
          fill="none"
          stroke="#F97316"
          stroke-width="2.2"
          stroke-linejoin="round"
        />

        <!-- Top rim highlight -->
        <rect x="28" y="64" width="624" height="6" rx="3" fill="none" stroke="#FFFFFF" stroke-opacity="0.14" stroke-width="1" />

        <!-- Zone typography (exact real numbers) -->
        <g class="zone-text" pointer-events="none">
          <!-- BROWSE -->
          <text x="152" y="106" text-anchor="middle" class="z-kicker">BROWSE</text>
          <text x="152" y="138" text-anchor="middle" class="z-num">{{ formatInt(metrics.view) }}</text>
          <text x="152" y="156" text-anchor="middle" class="z-sub">{{ formatPct(metrics.viewShare, 1) }} of valid</text>

          <!-- CART -->
          <text x="352" y="106" text-anchor="middle" class="z-kicker">CART</text>
          <text x="352" y="138" text-anchor="middle" class="z-num">{{ formatInt(metrics.cart) }}</text>
          <text x="352" y="156" text-anchor="middle" class="z-sub">{{ formatPct(metrics.cartShare, 1) }} of valid</text>

          <!-- OUTCOME -->
          <text x="542" y="106" text-anchor="middle" class="z-kicker">OUTCOME</text>
          <text x="542" y="138" text-anchor="middle" class="z-num">{{ formatInt(metrics.purchase) }}</text>
          <text x="542" y="156" text-anchor="middle" class="z-sub">{{ formatPct(metrics.overallPurchase, 2) }} of valid</text>
        </g>

        <!-- Interactive hover hit-targets per zone -->
        <rect
          x="32"
          y="64"
          width="224"
          height="182"
          fill="transparent"
          class="zone-hit"
          tabindex="0"
          @mouseenter="hovered = 'browse'"
          @mouseleave="hovered = null"
          @focus="hovered = 'browse'"
          @blur="hovered = null"
        />
        <rect
          x="256"
          y="64"
          width="192"
          height="182"
          fill="transparent"
          class="zone-hit"
          tabindex="0"
          @mouseenter="hovered = 'cart'"
          @mouseleave="hovered = null"
          @focus="hovered = 'cart'"
          @blur="hovered = null"
        />
        <rect
          x="448"
          y="64"
          width="202"
          height="182"
          fill="transparent"
          class="zone-hit"
          tabindex="0"
          @mouseenter="hovered = 'outcome'"
          @mouseleave="hovered = null"
          @focus="hovered = 'outcome'"
          @blur="hovered = null"
        />
      </svg>

      <!-- Floating hover tooltip -->
      <Transition name="fade">
        <div v-if="activeZone" class="funnel-tip" role="status">
          <div class="tip-head">
            <span class="tip-dot" :style="{ background: activeZone.color }" />
            <strong>{{ activeZone.title }}</strong>
            <span class="tip-count num">{{ formatInt(activeZone.count) }}</span>
          </div>
          <div class="tip-body">{{ activeZone.detail }}</div>
        </div>
      </Transition>
    </div>

    <!-- Right-hand Funnel Legend -->
    <aside class="funnel-legend" aria-label="Funnel stage breakdown">
      <div class="legend-title">Basket funnel (historical)</div>
      <div class="legend-valid">
        <span>Valid baseline</span>
        <strong class="num">{{ formatInt(metrics.valid) }} sessions</strong>
      </div>

      <div class="legend-items">
        <div
          class="legend-item"
          :class="{ active: hovered === 'browse' }"
          @mouseenter="hovered = 'browse'"
          @mouseleave="hovered = null"
        >
          <span class="l-dot" style="background: #3b82f6; box-shadow: 0 0 8px rgba(59, 130, 246, 0.7)" />
          <div class="l-copy">
            <div class="l-row">
              <span class="l-name">Browse (With View)</span>
              <span class="l-pct num">{{ formatPct(metrics.viewShare, 1) }}</span>
            </div>
            <div class="l-val num">{{ formatInt(metrics.view) }} sessions</div>
          </div>
        </div>

        <div
          class="legend-item"
          :class="{ active: hovered === 'cart' }"
          @mouseenter="hovered = 'cart'"
          @mouseleave="hovered = null"
        >
          <span class="l-dot" style="background: #d9f936; box-shadow: 0 0 8px rgba(217, 249, 54, 0.65)" />
          <div class="l-copy">
            <div class="l-row">
              <span class="l-name">Cart</span>
              <span class="l-pct num">{{ formatPct(metrics.cartShare, 1) }}</span>
            </div>
            <div class="l-val num">{{ formatInt(metrics.cart) }} sessions</div>
            <div class="l-note num">{{ formatPct(metrics.cartAbandon) }} cart abandonment</div>
          </div>
        </div>

        <div
          class="legend-item"
          :class="{ active: hovered === 'outcome' }"
          @mouseenter="hovered = 'outcome'"
          @mouseleave="hovered = null"
        >
          <span class="l-dot" style="background: #f97316; box-shadow: 0 0 8px rgba(249, 115, 22, 0.7)" />
          <div class="l-copy">
            <div class="l-row">
              <span class="l-name">Purchase</span>
              <span class="l-pct num">{{ formatPct(metrics.overallPurchase, 2) }}</span>
            </div>
            <div class="l-val num">{{ formatInt(metrics.purchase) }} sessions</div>
            <div class="l-note num">View → Purchase: {{ formatPct(metrics.viewToPurchase, 2) }}</div>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.funnel-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 268px;
  gap: 24px;
  align-items: center;
}

.basket-stage {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
}

.basket-svg {
  width: 100%;
  max-width: 760px;
  height: auto;
  display: block;
  overflow: visible;
}

.z-kicker {
  fill: #cbd5e1;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
}
.z-num {
  fill: #f8fafc;
  font-size: 24px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}
.z-sub {
  fill: #94a3b8;
  font-size: 11px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.zone-hit {
  cursor: pointer;
  outline: none;
}
.node-dot {
  transition: r 0.18s ease;
}

.funnel-tip {
  position: absolute;
  left: 50%;
  bottom: 4px;
  transform: translateX(-50%);
  background: rgba(10, 14, 22, 0.96);
  border: 1px solid var(--border-hover);
  border-radius: 10px;
  padding: 9px 13px;
  box-shadow: var(--shadow-pop);
  pointer-events: none;
  min-width: 280px;
  max-width: 92%;
  z-index: 5;
}
.tip-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
}
.tip-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}
.tip-count {
  margin-left: auto;
  color: var(--text);
  font-weight: 700;
}
.tip-body {
  font-size: 0.75rem;
  color: var(--text-2);
  margin-top: 3px;
}

.funnel-legend {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-left: 8px;
}
.legend-title {
  font-size: 0.96rem;
  font-weight: 650;
  color: var(--text);
}
.legend-valid {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 0.78rem;
  color: var(--text-3);
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.legend-valid strong {
  color: var(--text-2);
  font-weight: 600;
}

.legend-items {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.legend-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 10px;
  border: 1px solid transparent;
  transition: background 0.15s ease, border-color 0.15s ease;
  cursor: default;
}
.legend-item.active,
.legend-item:hover {
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--border);
}
.l-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  margin-top: 5px;
  flex-shrink: 0;
}
.l-copy {
  flex: 1;
  min-width: 0;
}
.l-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}
.l-name {
  font-size: 0.84rem;
  font-weight: 650;
  color: var(--text);
}
.l-pct {
  font-size: 0.76rem;
  color: var(--text-2);
  font-weight: 600;
}
.l-val {
  font-size: 0.8rem;
  color: var(--text-2);
  margin-top: 1px;
}
.l-note {
  font-size: 0.72rem;
  color: var(--text-3);
  margin-top: 2px;
}

@media (max-width: 960px) {
  .funnel-layout {
    grid-template-columns: 1fr;
  }
  .funnel-legend {
    padding-left: 0;
  }
  .legend-items {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .legend-items {
    grid-template-columns: 1fr;
  }
}
</style>
