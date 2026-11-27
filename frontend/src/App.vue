<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import {
  checkConnection,
  connectionStatus,
  dataSource,
  ENV_BASE_URL,
  resetSettings,
  retestConnection,
  setBaseUrl,
  setMode,
  settings,
} from '@/services/config'

const popoverOpen = ref(false)
const gearWrap = ref(null)
const urlDraft = ref(settings.baseUrl)
const testing = ref(false)

watch(
  () => settings.baseUrl,
  (v) => {
    urlDraft.value = v
  },
)

function togglePopover() {
  popoverOpen.value = !popoverOpen.value
  if (popoverOpen.value) urlDraft.value = settings.baseUrl
}

function applyUrl() {
  setBaseUrl(urlDraft.value)
}

async function handleRetest() {
  testing.value = true
  try {
    await retestConnection()
  } finally {
    testing.value = false
  }
}

function handleReset() {
  resetSettings()
  urlDraft.value = settings.baseUrl
}

function onDocClick(e) {
  if (!popoverOpen.value) return
  if (gearWrap.value && !gearWrap.value.contains(e.target)) {
    popoverOpen.value = false
  }
}

function onKeyDown(e) {
  if (e.key === 'Escape' && popoverOpen.value) popoverOpen.value = false
}

onMounted(() => {
  checkConnection()
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKeyDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKeyDown)
})

const modes = [
  { id: 'auto', label: 'Auto (Live + Mock fallback)' },
  { id: 'live', label: 'Live API Only' },
  { id: 'mock', label: 'Mock Data Mode' },
]
</script>

<template>
  <div class="shell">
    <header class="navbar">
      <div class="navbar-inner">
        <!-- Brand + live API status -->
        <div class="brand-cluster">
          <RouterLink to="/" class="brand" aria-label="DealMind AI home">
            <!-- Signature neon-lime wireframe shopping basket mark -->
            <svg class="brand-svg" viewBox="0 0 44 36" fill="none" aria-hidden="true">
              <path
                d="M15 13 L18.5 5.5 H25.5 L29 13"
                stroke="#D9F936"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M4 13 H40 L35.5 30.5 Q34.8 32.5 32.5 32.5 H11.5 Q9.2 32.5 8.5 30.5 Z"
                stroke="#D9F936"
                stroke-width="2"
                stroke-linejoin="round"
              />
              <path
                d="M6.2 19.5 H37.8 M7.7 26 H36.3 M13.5 13 L15 32.5 M22 13 V32.5 M30.5 13 L29 32.5"
                stroke="#D9F936"
                stroke-width="1.25"
                stroke-opacity="0.7"
              />
            </svg>
            <div class="brand-copy">
              <div class="brand-title">
                <span class="brand-name">DealMind AI</span>
                <span class="brand-sep" aria-hidden="true">|</span>
                <span class="brand-sub">Basket Intelligence</span>
              </div>
              <div class="status-line" :title="`Source: ${dataSource} (${settings.baseUrl || 'relative /api'})`">
                <span class="status-dot" :class="`tone-${connectionStatus.tone}`" aria-hidden="true" />
                <span class="status-label">{{ connectionStatus.label }}</span>
                <span class="status-sep" aria-hidden="true">|</span>
                <span class="status-detail">{{ connectionStatus.detail }}</span>
              </div>
            </div>
          </RouterLink>
        </div>

        <!-- Right navigation tabs + settings gear -->
        <div class="nav-right">
          <nav class="nav-tabs" aria-label="Primary">
            <RouterLink to="/" class="nav-tab" exact-active-class="active">Analytics</RouterLink>
            <RouterLink to="/replay" class="nav-tab" active-class="active">Session Replay</RouterLink>
            <RouterLink to="/models" class="nav-tab" active-class="active">Models</RouterLink>
          </nav>

          <div ref="gearWrap" class="gear-wrap">
            <button
              type="button"
              class="gear-btn"
              :class="{ open: popoverOpen }"
              aria-label="API and data source settings"
              :aria-expanded="popoverOpen"
              @click="togglePopover"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9">
                <circle cx="12" cy="12" r="3" />
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.26.6.77 1 1.43 1.07H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"
                />
              </svg>
            </button>

            <Transition name="fade">
              <div v-if="popoverOpen" class="settings-popover" role="dialog" aria-label="Connection settings">
                <div class="pop-head">
                  <div>
                    <div class="pop-title">Data Connection</div>
                    <div class="pop-sub">Switch between FastAPI &amp; local SQLite snapshot</div>
                  </div>
                  <span class="badge" :class="dataSource === 'live' ? 'badge-green' : 'badge-amber'">
                    {{ dataSource === 'live' ? 'Live' : 'Mock' }}
                  </span>
                </div>

                <div class="pop-section">
                  <div class="eyebrow">Source Mode</div>
                  <div class="mode-list">
                    <button
                      v-for="m in modes"
                      :key="m.id"
                      type="button"
                      class="mode-opt"
                      :class="{ active: settings.mode === m.id }"
                      @click="setMode(m.id)"
                    >
                      <span class="radio-dot" />
                      <span>{{ m.label }}</span>
                    </button>
                  </div>
                </div>

                <div class="pop-section">
                  <label class="eyebrow" for="api-base-input">API Base URL</label>
                  <form class="url-row" @submit.prevent="applyUrl">
                    <input
                      id="api-base-input"
                      v-model="urlDraft"
                      type="url"
                      class="url-input mono"
                      :placeholder="ENV_BASE_URL || 'http://localhost:8000'"
                      spellcheck="false"
                    />
                    <button type="submit" class="btn btn-sm btn-blue">Apply</button>
                  </form>
                  <div class="pop-hint">
                    Leave blank for relative <span class="mono">/api</span> proxy.
                  </div>
                </div>

                <div class="pop-foot">
                  <button type="button" class="btn btn-sm" :disabled="testing || settings.mode === 'mock'" @click="handleRetest">
                    {{ testing ? 'Checking…' : 'Test /api/health' }}
                  </button>
                  <button type="button" class="btn btn-sm btn-ghost" @click="handleReset">Reset</button>
                </div>
              </div>
            </Transition>
          </div>
        </div>
      </div>
    </header>

    <main class="main-wrap">
      <RouterView v-slot="{ Component }">
        <Transition name="page" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>

    <footer class="site-footer">
      <div class="footer-inner">
        <span>
          DealMind AI · Historical E-Commerce Analysis (Oct 2019 – Feb 2020) · Zero-Leakage Temporal Split · Recorded Price Units (No Currency Assumed) · All Timestamps in UTC
        </span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.navbar {
  position: sticky;
  top: 0;
  z-index: 40;
  background: rgba(7, 10, 15, 0.88);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
}

.navbar-inner {
  max-width: var(--page-max);
  margin: 0 auto;
  padding: 12px var(--page-pad);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-svg {
  width: 38px;
  height: 32px;
  flex-shrink: 0;
  filter: drop-shadow(0 0 8px rgba(217, 249, 54, 0.25));
}

.brand-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.brand-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.brand-name {
  font-size: 1.08rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
}

.brand-sep {
  color: var(--text-3);
  font-weight: 300;
}

.brand-sub {
  font-size: 0.92rem;
  font-weight: 500;
  color: var(--text-2);
}

.status-line {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72rem;
  line-height: 1.2;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  flex-shrink: 0;
}
.tone-green {
  background: var(--success);
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.8);
}
.tone-amber {
  background: var(--warning);
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.7);
}
.tone-red {
  background: var(--danger);
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.7);
}
.tone-muted {
  background: var(--text-3);
}

.status-label {
  color: var(--text);
  font-weight: 600;
}
.status-sep {
  color: var(--text-3);
}
.status-detail {
  color: var(--text-2);
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.nav-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
}

.nav-tab {
  padding: 7px 15px;
  border-radius: 9px;
  font-size: 0.84rem;
  font-weight: 600;
  color: var(--text-2);
  border: 1px solid transparent;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}

.nav-tab:hover {
  color: var(--text);
  background: rgba(255, 255, 255, 0.04);
}

.nav-tab.active {
  background: var(--browse);
  color: #fff;
  border-color: rgba(59, 130, 246, 0.6);
  box-shadow: 0 0 20px rgba(37, 99, 235, 0.35);
}

.gear-wrap {
  position: relative;
}

.gear-btn {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  color: var(--text-2);
  border: 1px solid var(--border);
  background: var(--bg-card);
  transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}
.gear-btn:hover,
.gear-btn.open {
  color: var(--text);
  border-color: var(--border-hover);
  background: var(--bg-elev);
}

.settings-popover {
  position: absolute;
  right: 0;
  top: calc(100% + 10px);
  width: min(330px, calc(100vw - 32px));
  background: var(--bg-card);
  border: 1px solid var(--border-hover);
  border-radius: 14px;
  padding: 16px;
  box-shadow: var(--shadow-pop);
  display: flex;
  flex-direction: column;
  gap: 14px;
  z-index: 60;
}

.pop-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}
.pop-title {
  font-size: 0.9rem;
  font-weight: 650;
}
.pop-sub {
  font-size: 0.74rem;
  color: var(--text-2);
}

.pop-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mode-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.mode-opt {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: var(--bg-card-2);
  font-size: 0.8rem;
  color: var(--text-2);
  text-align: left;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.mode-opt:hover {
  border-color: var(--border-hover);
  color: var(--text);
}
.mode-opt.active {
  border-color: rgba(59, 130, 246, 0.55);
  background: rgba(37, 99, 235, 0.12);
  color: var(--text);
  font-weight: 600;
}
.radio-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  border: 2px solid var(--text-3);
  flex-shrink: 0;
}
.mode-opt.active .radio-dot {
  border-color: var(--browse-2);
  background: radial-gradient(circle, var(--browse-2) 45%, transparent 50%);
}

.url-row {
  display: flex;
  gap: 6px;
}
.url-input {
  flex: 1;
  min-width: 0;
  padding: 7px 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-canvas);
  color: var(--text);
  font-size: 0.78rem;
}
.url-input:focus {
  outline: none;
  border-color: var(--browse-2);
}
.pop-hint {
  font-size: 0.72rem;
  color: var(--text-3);
}

.pop-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.main-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.site-footer {
  border-top: 1px solid var(--border);
  background: rgba(7, 10, 15, 0.7);
}
.footer-inner {
  max-width: var(--page-max);
  margin: 0 auto;
  padding: 13px var(--page-pad);
  font-size: 0.74rem;
  color: var(--text-3);
  text-align: center;
}
</style>
