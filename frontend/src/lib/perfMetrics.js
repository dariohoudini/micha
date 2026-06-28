/**
 * perfMetrics — client RUM reporting (Mobile App Engineering CH24).
 *
 * Feeds the mobile KPI dashboard (apps/mobile_app MobileKpiSnapshot):
 *   cold_start_ms — navigationStart → app interactive (reported once,
 *                   from main.jsx right after the first render)
 *   api_success / api_failure — counters incremented by client.js
 *   screen_render_ms — optional per-screen samples via recordScreenRender
 *
 * Samples buffer in memory and flush to POST /api/v1/mobile/perf/batch/
 * every 60s and on background (sendBeacon). Loss-tolerant by design —
 * a dropped batch only thins the percentile sample, never breaks UX.
 */
import { getFingerprint } from '@/api/fingerprint'

const FLUSH_INTERVAL_MS = 60_000

let _samples = []
let _apiSuccess = 0
let _apiFailure = 0
let _started = false
let _fingerprint = ''

function base() {
  return {
    platform: window.Capacitor?.getPlatform?.() || 'web',
    app_version: import.meta.env?.VITE_APP_VERSION || 'dev',
    device_model: navigator.userAgent.slice(0, 64),
    device_class: deviceClass(),
    network_type: navigator.connection?.effectiveType || 'unknown',
  }
}

/* Coarse device banding — mirrors the doc's "mid-range Android" focus. */
function deviceClass() {
  try {
    const mem = navigator.deviceMemory || 4
    if (mem <= 2) return 'low'
    if (mem <= 4) return 'mid'
    return 'high'
  } catch { return 'mid' }
}

export function recordColdStart() {
  try {
    const nav = performance.getEntriesByType('navigation')[0]
    const ms = nav ? nav.domInteractive : performance.now()
    if (ms > 0 && ms < 120_000) {
      _samples.push({ metric: 'cold_start_ms', value: Math.round(ms), ...base() })
    }
  } catch {}
}

export function recordScreenRender(screen, ms) {
  _samples.push({ metric: 'screen_render_ms', value: Math.round(ms),
    screen: String(screen).slice(0, 64), ...base() })
}

/** client.js calls these on every API response/error. */
export function recordApiSuccess() { _apiSuccess++ }
export function recordApiFailure() { _apiFailure++ }

export async function flushPerf({ useBeacon = false } = {}) {
  const samples = [..._samples]
  if (_apiSuccess > 0) {
    samples.push({ metric: 'api_success', value: _apiSuccess, ...base() })
  }
  if (_apiFailure > 0) {
    samples.push({ metric: 'api_failure', value: _apiFailure, ...base() })
  }
  if (samples.length === 0) return { flushed: 0 }
  _samples = []
  _apiSuccess = 0
  _apiFailure = 0

  const body = JSON.stringify({ samples })
  const url = `${import.meta.env.VITE_API_BASE_URL || ''}/api/v1/mobile/perf/batch/`
  if (useBeacon && navigator.sendBeacon) {
    navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }))
    return { flushed: samples.length }
  }
  try {
    const { default: client } = await import('@/api/client')
    await client.post('/api/v1/mobile/perf/batch/', { samples })
    return { flushed: samples.length }
  } catch {
    return { flushed: 0 }  // loss-tolerant: drop rather than grow unbounded
  }
}

/** Call once from main.jsx after first render. */
export async function initPerfMetrics() {
  if (_started) return
  _started = true
  try { _fingerprint = await getFingerprint() } catch {}
  recordColdStart()
  setInterval(() => { flushPerf() }, FLUSH_INTERVAL_MS)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushPerf({ useBeacon: true })
  })
}
