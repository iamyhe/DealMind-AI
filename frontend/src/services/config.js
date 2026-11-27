import { computed, reactive } from 'vue'

/**
 * Global runtime settings + API connection state.
 * mode: 'auto' (live API with mock fallback) | 'live' (live only) | 'mock' (bundled mock data only)
 */
const LS_KEY = 'dealmind.settings.v1'
const DEFAULT_BASE = 'http://localhost:8000'

const envBase = import.meta.env.VITE_API_BASE_URL
// undefined -> default; '' -> relative (Vite dev proxy forwards /api)
export const ENV_BASE_URL = envBase === undefined ? DEFAULT_BASE : String(envBase).trim()

function envMode() {
  const v = String(import.meta.env.VITE_USE_MOCK ?? 'auto').trim().toLowerCase()
  if (['true', '1', 'mock', 'yes'].includes(v)) return 'mock'
  if (['false', '0', 'live', 'no'].includes(v)) return 'live'
  return 'auto'
}
export const ENV_MODE = envMode()

function loadPersisted() {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return {}
    const p = JSON.parse(raw)
    return {
      mode: ['auto', 'live', 'mock'].includes(p.mode) ? p.mode : undefined,
      baseUrl: typeof p.baseUrl === 'string' ? p.baseUrl : undefined,
    }
  } catch {
    return {}
  }
}

const persisted = loadPersisted()

export const settings = reactive({
  mode: persisted.mode ?? ENV_MODE,
  baseUrl: normalizeBase(persisted.baseUrl ?? ENV_BASE_URL),
  /** 'idle' | 'checking' | 'connected' | 'unreachable' */
  connection: 'idle',
  lastChecked: null,
  lastError: null,
  /** bump to make views refetch after settings change */
  dataVersion: 0,
})

export function normalizeBase(url) {
  return String(url ?? '')
    .trim()
    .replace(/\/+$/, '')
}

function persist() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ mode: settings.mode, baseUrl: settings.baseUrl }))
  } catch {
    /* storage unavailable — ignore */
  }
}

/** Effective data source right now. */
export const dataSource = computed(() => {
  if (settings.mode === 'mock') return 'mock'
  if (settings.mode === 'live') return 'live'
  return settings.connection === 'connected' ? 'live' : 'mock'
})

/** UI status for the navbar indicator. */
export const connectionStatus = computed(() => {
  if (settings.mode === 'mock') return { tone: 'amber', label: 'Mock Mode', detail: 'Local Preview' }
  if (settings.connection === 'checking' || settings.connection === 'idle')
    return { tone: 'muted', label: 'Connecting…', detail: settings.baseUrl || 'relative /api' }
  if (settings.connection === 'connected') return { tone: 'green', label: 'API Connected', detail: 'FastAPI Local' }
  if (settings.mode === 'live') return { tone: 'red', label: 'API Unreachable', detail: 'Live API Only' }
  return { tone: 'amber', label: 'Mock Mode', detail: 'Local Preview' }
})

let healthPromise = null
let healthListeners = []

/** Register the health-check implementation (set by api.js to avoid a circular import). */
export function onHealthCheck(fn) {
  healthListeners = [fn]
}

/** Run (or join) a health check. Resolves to true when the API is reachable. */
export function checkConnection() {
  if (settings.mode === 'mock') {
    settings.connection = 'idle'
    return Promise.resolve(false)
  }
  if (healthPromise) return healthPromise
  const fn = healthListeners[0]
  if (!fn) return Promise.resolve(false)
  if (settings.connection !== 'connected') settings.connection = 'checking'
  healthPromise = fn()
    .then((ok) => {
      settings.connection = ok ? 'connected' : 'unreachable'
      settings.lastError = ok ? null : 'Health check failed'
      return ok
    })
    .catch((e) => {
      settings.connection = 'unreachable'
      settings.lastError = e?.message || 'Network error'
      return false
    })
    .finally(() => {
      settings.lastChecked = new Date()
      healthPromise = null
    })
  return healthPromise
}

/** Await the source that should serve the next request. */
export async function resolveSource() {
  if (settings.mode === 'mock') return 'mock'
  if (settings.connection === 'idle' || settings.connection === 'checking') await checkConnection()
  return dataSource.value
}

export function markUnreachable(err) {
  settings.connection = 'unreachable'
  settings.lastError = err?.message || 'Network error'
}

const cacheClearers = new Set()
export function registerCache(clearFn) {
  cacheClearers.add(clearFn)
}

function invalidate() {
  cacheClearers.forEach((fn) => fn())
  settings.dataVersion += 1
}

export function setMode(mode) {
  if (!['auto', 'live', 'mock'].includes(mode) || mode === settings.mode) return
  settings.mode = mode
  settings.connection = 'idle'
  persist()
  invalidate()
  checkConnection()
}

export function setBaseUrl(url) {
  const next = normalizeBase(url)
  if (next === settings.baseUrl) return
  settings.baseUrl = next
  settings.connection = 'idle'
  persist()
  invalidate()
  checkConnection()
}

export function resetSettings() {
  settings.mode = ENV_MODE
  settings.baseUrl = normalizeBase(ENV_BASE_URL)
  settings.connection = 'idle'
  try {
    localStorage.removeItem(LS_KEY)
  } catch {
    /* ignore */
  }
  invalidate()
  checkConnection()
}

/** Re-test connectivity; if the effective source changes, views refetch. */
export async function retestConnection() {
  const before = dataSource.value
  await checkConnection()
  if (dataSource.value !== before) invalidate()
}
