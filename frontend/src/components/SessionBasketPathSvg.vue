<script setup>
import { computed, ref, useId } from 'vue'
import { formatEventType, formatPriceUnits, formatUtcClock } from '@/utils/formatters'

const props = defineProps({
  session: { type: Object, required: true },
  safeEvents: { type: Array, default: () => [] },
  revealed: { type: Boolean, default: false },
  actualOutcome: { type: Number, default: null },
  postEvents: { type: Array, default: () => [] },
})

const uid = useId()
const hoveredNode = ref(null)

const hRibs = [76, 98, 120, 142, 164, 186, 206]
const vRibs = Array.from({ length: 17 }, (_, i) => {
  const t = i / 16
  return { xTop: 44 + t * 592, xBot: 90 + t * 500 }
})

const preEvents = computed(() => props.safeEvents.filter((e) => e.event_phase === 'before_first_cart'))
const cartEvents = computed(() =>
  props.safeEvents.filter((e) => e.event_phase === 'at_first_cart_second' || e.event_phase === 'same_second_other'),
)

function smoothPath(pts) {
  if (!pts.length) return ''
  if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y}`
  let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`
  for (let i = 1; i < pts.length; i++) {
    const p0 = pts[i - 1]
    const p1 = pts[i]
    const mx = ((p0.x + p1.x) / 2).toFixed(1)
    d += ` C ${mx} ${p0.y.toFixed(1)}, ${mx} ${p1.y.toFixed(1)}, ${p1.x.toFixed(1)} ${p1.y.toFixed(1)}`
  }
  return d
}

// Cap plotted nodes cleanly if a long session has dozens of events, while keeping first/last/purchases
function sampleEvents(arr, max = 9) {
  if (arr.length <= max) return arr.map((e, i) => ({ ev: e, idx: i }))
  const step = (arr.length - 1) / (max - 1)
  const picked = []
  const seen = new Set()
  for (let i = 0; i < max; i++) {
    const idx = Math.round(i * step)
    if (!seen.has(idx)) {
      seen.add(idx)
      picked.push({ ev: arr[idx], idx })
    }
  }
  return picked
}

const browseNodes = computed(() => {
  const list = sampleEvents(preEvents.value, 8)
  if (!list.length) return []
  return list.map(({ ev }, i) => {
    const t = list.length === 1 ? 0.55 : i / (list.length - 1)
    const x = 84 + t * 144
    const y = 132 + Math.sin(t * Math.PI * 1.15) * 18 + t * 22
    const isRemove = ev.event_type === 'remove_from_cart'
    return {
      key: `pre-${ev.id ?? i}`,
      x,
      y,
      r: isRemove ? 5.2 : 5.5,
      color: isRemove ? '#F59E0B' : '#3B82F6',
      ev,
      phaseLabel: 'Pre-cart',
    }
  })
})

const cartNodes = computed(() => {
  const list = cartEvents.value.length ? cartEvents.value.slice(0, 3) : [{ event_type: 'cart', product_id: props.session?.cart_product_ids_at_first_cart_sec, price: props.session?.avg_cart_price_at_first_cart_sec, event_time: props.session?.first_cart_time }]
  return list.map((ev, i) => {
    const t = list.length === 1 ? 0.5 : i / (list.length - 1)
    const x = list.length === 1 ? 344 : 302 + t * 84
    const y = 166 + (i % 2 === 0 ? 0 : 10)
    return {
      key: `cart-${ev.id ?? i}`,
      x,
      y,
      r: 7,
      color: '#D9F936',
      ev,
      phaseLabel: 'First cart moment',
    }
  })
})

const postNodes = computed(() => {
  if (!props.revealed) return []
  const list = sampleEvents(props.postEvents, 7)
  if (!list.length) {
    return [
      {
        key: 'outcome-end',
        x: 562,
        y: 196,
        r: 7.5,
        color: props.actualOutcome === 1 ? '#22C55E' : '#EF4444',
        synthetic: true,
        label: props.actualOutcome === 1 ? 'Purchased (1)' : 'Abandoned · no further events',
      },
    ]
  }
  return list.map(({ ev }, i) => {
    const t = list.length === 1 ? 0.55 : i / (list.length - 1)
    const x = 472 + t * 116
    const y = 180 + Math.sin(t * Math.PI) * 10 + t * 14
    const color =
      ev.event_type === 'purchase'
        ? '#22C55E'
        : ev.event_type === 'cart'
          ? '#D9F936'
          : ev.event_type === 'remove_from_cart'
            ? '#EF4444'
            : '#FB923C'
    return {
      key: `post-${ev.id ?? i}`,
      x,
      y,
      r: ev.event_type === 'purchase' ? 7.5 : 5,
      color,
      ev,
      phaseLabel: 'Post-cart outcome',
    }
  })
})

const safeCurvePath = computed(() => {
  const pts = [...browseNodes.value, ...cartNodes.value]
  if (!browseNodes.value.length && cartNodes.value.length) {
    // Direct-to-cart dashed lead-in
    const c = cartNodes.value[0]
    return smoothPath([{ x: 96, y: 152 }, c, ...cartNodes.value.slice(1)])
  }
  return smoothPath(pts)
})

const postCurvePath = computed(() => {
  const lastCart = cartNodes.value[cartNodes.value.length - 1]
  if (!lastCart) return ''
  if (!props.revealed) {
    return smoothPath([lastCart, { x: 492, y: 184 }, { x: 568, y: 195 }])
  }
  return smoothPath([lastCart, ...postNodes.value])
})

const allInteractiveNodes = computed(() => [...browseNodes.value, ...cartNodes.value, ...postNodes.value])
</script>

<template>
  <div class="sb-wrap">
    <svg
      class="sb-svg"
      viewBox="0 0 680 242"
      role="img"
      :aria-label="`Basket journey for ${session?.id}: ${preEvents.length} pre-cart events, ${cartEvents.length} first-cart events`"
    >
      <defs>
        <clipPath :id="`${uid}-shell`">
          <path d="M 32 60 L 648 60 L 598 214 Q 593 228 576 228 L 104 228 Q 87 228 82 214 Z" />
        </clipPath>
        <clipPath :id="`${uid}-z1`"><rect x="0" y="45" width="256" height="195" /></clipPath>
        <clipPath :id="`${uid}-z2`"><rect x="256" y="45" width="182" height="195" /></clipPath>
        <clipPath :id="`${uid}-z3`"><rect x="438" y="45" width="242" height="195" /></clipPath>

        <linearGradient :id="`${uid}-safegrad`" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#3B82F6" />
          <stop offset="100%" stop-color="#D9F936" />
        </linearGradient>

        <filter :id="`${uid}-glow`" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2.8" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <!-- Top handle -->
      <path
        d="M 232 56 L 262 12 Q 266 7 274 7 L 406 7 Q 414 7 418 12 L 448 56"
        fill="none"
        stroke="#475569"
        stroke-width="9"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <path
        d="M 236 56 L 265 14 Q 268 10 275 10 L 405 10 Q 412 10 415 14 L 444 56"
        fill="none"
        stroke="#94A3B8"
        stroke-opacity="0.35"
        stroke-width="1.8"
        stroke-linecap="round"
      />
      <path d="M 46 54 Q 340 44 634 54" fill="none" stroke="#334155" stroke-opacity="0.65" stroke-width="1.8" />

      <g :clip-path="`url(#${uid}-shell)`">
        <!-- Zone 1: BROWSE (Blue) -->
        <g :clip-path="`url(#${uid}-z1)`">
          <rect x="0" y="54" width="256" height="180" fill="#2563EB" fill-opacity="0.08" />
          <line v-for="y in hRibs" :key="`b-h-${y}`" x1="28" :y1="y" x2="652" :y2="y" stroke="#3B82F6" stroke-opacity="0.28" stroke-width="1" />
          <line v-for="(r, i) in vRibs" :key="`b-v-${i}`" :x1="r.xTop" y1="58" :x2="r.xBot" y2="230" stroke="#3B82F6" stroke-opacity="0.32" stroke-width="1" />
        </g>

        <!-- Zone 2: CART (Acid Lime) -->
        <g :clip-path="`url(#${uid}-z2)`">
          <rect x="256" y="54" width="182" height="180" fill="#D9F936" fill-opacity="0.07" />
          <line v-for="y in hRibs" :key="`c-h-${y}`" x1="28" :y1="y" x2="652" :y2="y" stroke="#D9F936" stroke-opacity="0.26" stroke-width="1" />
          <line v-for="(r, i) in vRibs" :key="`c-v-${i}`" :x1="r.xTop" y1="58" :x2="r.xBot" y2="230" stroke="#D9F936" stroke-opacity="0.3" stroke-width="1" />
        </g>

        <!-- Zone 3: OUTCOME (Vivid Orange — dimmed until revealed) -->
        <g :clip-path="`url(#${uid}-z3)`" :opacity="revealed ? 0.95 : 0.28" style="transition: opacity 0.35s ease">
          <rect
            x="438"
            y="54"
            width="242"
            height="180"
            :fill="revealed && actualOutcome === 1 ? '#22C55E' : '#F97316'"
            :fill-opacity="revealed ? 0.1 : 0.05"
          />
          <line
            v-for="y in hRibs"
            :key="`o-h-${y}`"
            x1="28"
            :y1="y"
            x2="652"
            :y2="y"
            :stroke="revealed && actualOutcome === 1 ? '#22C55E' : '#F97316'"
            stroke-opacity="0.3"
            stroke-width="1"
          />
          <line
            v-for="(r, i) in vRibs"
            :key="`o-v-${i}`"
            :x1="r.xTop"
            y1="58"
            :x2="r.xBot"
            y2="230"
            :stroke="revealed && actualOutcome === 1 ? '#22C55E' : '#F97316'"
            stroke-opacity="0.34"
            stroke-width="1"
          />
        </g>

        <!-- Zone divider + dashed orange PREDICTION CUTOFF line -->
        <line x1="256" y1="60" x2="256" y2="228" stroke="#D9F936" stroke-opacity="0.45" stroke-width="1.3" />
        <line
          x1="438"
          y1="60"
          x2="438"
          y2="228"
          stroke="#F97316"
          stroke-width="1.7"
          stroke-dasharray="5 4"
          :stroke-opacity="revealed ? 0.85 : 0.95"
        />

        <!-- Safe path curve (dashed if direct-to-cart with 0 pre-cart events) -->
        <path
          v-if="safeCurvePath"
          :d="safeCurvePath"
          fill="none"
          :stroke="browseNodes.length ? `url(#${uid}-safegrad)` : '#D9F936'"
          stroke-width="2.5"
          stroke-linecap="round"
          :stroke-dasharray="browseNodes.length ? undefined : '5 4'"
          :filter="`url(#${uid}-glow)`"
        />

        <!-- Post-cart curve: locked dashed gray before reveal, glowing solid after reveal -->
        <path
          v-if="postCurvePath"
          :d="postCurvePath"
          fill="none"
          :stroke="revealed ? (actualOutcome === 1 ? '#22C55E' : '#F97316') : '#64748B'"
          :stroke-width="revealed ? 2.5 : 1.7"
          :stroke-dasharray="revealed ? undefined : '4 5'"
          :stroke-opacity="revealed ? 0.95 : 0.5"
          stroke-linecap="round"
        />

        <!-- Direct-to-cart tag when 0 pre-cart events -->
        <text v-if="!browseNodes.length" x="150" y="138" text-anchor="middle" class="direct-note">
          Direct to cart (0 prior events)
        </text>

        <!-- Outcome withheld badge inside right zone before reveal -->
        <g v-if="!revealed" pointer-events="none">
          <rect x="486" y="132" width="122" height="28" rx="14" fill="#0B0F17" fill-opacity="0.88" stroke="#F97316" stroke-opacity="0.45" />
          <text x="547" y="150" text-anchor="middle" class="lock-label">OUTCOME WITHHELD</text>
        </g>

        <!-- Interactive nodes -->
        <g
          v-for="n in allInteractiveNodes"
          :key="n.key"
          class="sb-node"
          @mouseenter="hoveredNode = n"
          @mouseleave="hoveredNode = null"
        >
          <circle :cx="n.x" :cy="n.y" :r="n.r + 5" :fill="n.color" fill-opacity="0.18" />
          <circle
            :cx="n.x"
            :cy="n.y"
            :r="hoveredNode?.key === n.key ? n.r + 1.8 : n.r"
            :fill="n.color"
            stroke="#070A0F"
            stroke-width="1.6"
          />
        </g>
      </g>

      <!-- Outer wireframe rim -->
      <path
        d="M 256 60 L 36 60 Q 28 60 32 70 L 82 214 Q 87 228 104 228 L 256 228"
        fill="none"
        stroke="#3B82F6"
        stroke-width="2"
        stroke-linejoin="round"
      />
      <path d="M 256 60 L 438 60 M 256 228 L 438 228" fill="none" stroke="#D9F936" stroke-width="2" />
      <path
        d="M 438 60 L 644 60 Q 652 60 648 70 L 598 214 Q 593 228 576 228 L 438 228"
        fill="none"
        :stroke="revealed && actualOutcome === 1 ? '#22C55E' : '#F97316'"
        :stroke-opacity="revealed ? 0.95 : 0.45"
        stroke-width="2"
        stroke-linejoin="round"
        style="transition: stroke-opacity 0.35s ease, stroke 0.35s ease"
      />

      <!-- Zone titles -->
      <g pointer-events="none">
        <text x="150" y="92" text-anchor="middle" class="z-head">BROWSE</text>
        <text x="347" y="92" text-anchor="middle" class="z-head">CART</text>
        <text x="546" y="92" text-anchor="middle" class="z-head" :opacity="revealed ? 1 : 0.55">OUTCOME</text>
      </g>
    </svg>

    <!-- Node hover tooltip -->
    <Transition name="fade">
      <div v-if="hoveredNode" class="sb-tip">
        <template v-if="hoveredNode.synthetic">
          <span class="badge" :class="actualOutcome === 1 ? 'badge-green' : 'badge-red'">{{ hoveredNode.label }}</span>
        </template>
        <template v-else>
          <span class="tip-type">{{ formatEventType(hoveredNode.ev.event_type) }}</span>
          <span class="mono">Product #{{ hoveredNode.ev.product_id }}</span>
          <span class="muted">·</span>
          <span>{{ hoveredNode.ev.brand || 'Unlisted brand' }}</span>
          <span class="muted">·</span>
          <span class="num">{{ formatPriceUnits(hoveredNode.ev.price) }} units</span>
          <span class="muted">·</span>
          <span class="num muted">{{ formatUtcClock(hoveredNode.ev.event_time) }} UTC</span>
        </template>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.sb-wrap {
  position: relative;
  display: flex;
  justify-content: center;
  padding: 4px 0;
}
.sb-svg {
  width: 100%;
  max-width: 680px;
  height: auto;
  display: block;
}
.z-head {
  fill: #e2e8f0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
}
.direct-note {
  fill: #64748b;
  font-size: 11.5px;
  font-weight: 500;
}
.lock-label {
  fill: #fdba74;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.1em;
}
.sb-node {
  cursor: pointer;
}
.sb-tip {
  position: absolute;
  bottom: 2px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
  background: rgba(10, 14, 22, 0.96);
  border: 1px solid var(--border-hover);
  border-radius: 9px;
  padding: 6px 12px;
  font-size: 0.75rem;
  color: var(--text-2);
  box-shadow: var(--shadow-pop);
  pointer-events: none;
  white-space: nowrap;
}
.tip-type {
  font-weight: 700;
  color: var(--text);
}
</style>
