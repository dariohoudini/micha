/**
 * eventBatch — mobile analytics event batching (Mobile App Engineering CH20).
 *
 * Every event carries the mobile base schema (event_id, session, device
 * fingerprint, platform, network, locale, active A/B variants) and is
 * buffered locally, then flushed to POST /api/v1/mobile/events/batch/:
 *   • every 30 seconds, or
 *   • when the app goes to background (visibilitychange → hidden),
 *     via navigator.sendBeacon so the request survives the page freeze.
 *
 * The server dedupes by event_id, so a retry after a network failure
 * never double-counts. Buffer is persisted to localStorage — events
 * fired right before a crash/kill are delivered on next launch.
 *
 * This complements lib/events.js (per-event PostHog + legacy sink):
 * events.js calls enqueueEvent() so both pipelines see every event.
 */
import { getFingerprint } from '@/api/fingerprint'

const BUFFER_KEY = 'micha_event_buffer_v1'
const SESSION_KEY = 'micha_session_id'
const FLUSH_INTERVAL_MS = 30_000
const MAX_BUFFER = 500           // hard cap — drop oldest beyond this
const MAX_BATCH = 100            // server limit per request

let _buffer = []
let _timer = null
let _fingerprint = ''
let _started = false

function loadBuffer() {
  try {
    const raw = localStorage.getItem(BUFFER_KEY)
    if (raw) _buffer = JSON.parse(raw)
  } catch { _buffer = [] }
}

function persistBuffer() {
  try { localStorage.setItem(BUFFER_KEY, JSON.stringify(_buffer)) } catch {}
}

export function getSessionId() {
  try {
    let sid = sessionStorage.getItem(SESSION_KEY)
    if (!sid) {
      sid = crypto.randomUUID()
      sessionStorage.setItem(SESSION_KEY, sid)
    }
    return sid
  } catch { return 'no-session' }
}

function platform() {
  try {
    const cap = window.Capacitor
    if (cap?.getPlatform) return cap.getPlatform()  // ios | android | web
  } catch {}
  return 'web'
}

function networkType() {
  try {
    if (!navigator.onLine) return 'none'
    return navigator.connection?.effectiveType || 'unknown'
  } catch { return 'unknown' }
}

// abClient registers a provider at init — avoids an import cycle
// (abClient → eventBatch for exposures, eventBatch → abClient here).
let _variantsProvider = () => ({})
export function setVariantsProvider(fn) { _variantsProvider = fn }

/** Add one event to the buffer with the full base schema (doc CH20). */
export function enqueueEvent(eventName, properties = {}, eventCategory = '') {
  let abVariants = {}
  try { abVariants = _variantsProvider() || {} } catch {}
  _buffer.push({
    event_id: crypto.randomUUID(),
    session_id: getSessionId(),
    device_fp: _fingerprint,
    platform: platform(),
    app_version: import.meta.env?.VITE_APP_VERSION || 'dev',
    os_version: '',
    device_model: navigator.userAgent.slice(0, 64),
    network_type: networkType(),
    locale: navigator.language || 'pt-AO',
    ab_variants: abVariants,
    event_name: String(eventName).slice(0, 64),
    event_category: String(eventCategory).slice(0, 32),
    properties,
    event_time: Date.now(),
  })
  if (_buffer.length > MAX_BUFFER) _buffer = _buffer.slice(-MAX_BUFFER)
  persistBuffer()
}

/** Flush up to MAX_BATCH events. Keeps the rest for the next cycle. */
export async function flushEvents({ useBeacon = false } = {}) {
  if (_buffer.length === 0) return { flushed: 0 }
  const batch = _buffer.slice(0, MAX_BATCH)
  const body = JSON.stringify({ events: batch })
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const url = `${base}/api/v1/mobile/events/batch/`

  if (useBeacon && navigator.sendBeacon) {
    // Background flush — fire and forget; server dedup makes a
    // possible re-send on next launch harmless.
    const ok = navigator.sendBeacon(
      url, new Blob([body], { type: 'application/json' }))
    if (ok) {
      _buffer = _buffer.slice(batch.length)
      persistBuffer()
    }
    return { flushed: ok ? batch.length : 0 }
  }

  try {
    const { default: client } = await import('@/api/client')
    await client.post('/api/v1/mobile/events/batch/', { events: batch })
    _buffer = _buffer.slice(batch.length)
    persistBuffer()
    return { flushed: batch.length }
  } catch {
    return { flushed: 0 }  // keep buffered; next cycle retries
  }
}

/** Start the 30s flush loop + background flush. Call once from main.jsx. */
export async function initEventBatching() {
  if (_started) return
  _started = true
  loadBuffer()
  try { _fingerprint = await getFingerprint() } catch {}
  _timer = setInterval(() => { flushEvents() }, FLUSH_INTERVAL_MS)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      flushEvents({ useBeacon: true })
    }
  })
}

export function _resetForTests() {
  _buffer = []
  _started = false
  if (_timer) clearInterval(_timer)
}
