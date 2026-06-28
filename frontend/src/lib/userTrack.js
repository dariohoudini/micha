/**
 * userTrack — every-touch DB telemetry per User Process Flow §20.8.
 *
 * The MICHA User Process Flow doc lists "Data Written / Where Stored
 * / Cross-Feature Impact" tables for nearly every interaction. To
 * make those work end-to-end we need a single, reliable client API:
 *
 *   import { track } from '@/lib/userTrack'
 *   track('product.view', { product_id: 42, source: 'home_feed' })
 *
 * Persistence guarantees
 * ──────────────────────
 *  1. Best-effort online send to `/api/v1/analytics/events/` (the
 *     batched ingest endpoint that writes to the `UserEvent` table).
 *  2. Offline / failure queue in localStorage — drained on next
 *     successful send. Survives app cold-start.
 *  3. Batching: events are buffered for up to 800ms or 8 events,
 *     then flushed as a single POST. Reduces request volume.
 *  4. Session ID stable per app boot — created lazily, stored in
 *     sessionStorage so refreshes keep it, restarts reset it.
 *  5. PII never leaves the client unscrubbed: a local denylist
 *     strips the same keys the backend redacts.
 *
 * Why no third-party SDK
 * ──────────────────────
 *  • Vendor lock-in.
 *  • The doc explicitly requires DB persistence, not just an
 *    external analytics dashboard.
 *  • Anything we send to PostHog/Mixpanel would ALSO need to land
 *    in our own DB for retention/legal use-cases.
 *
 * Convention for event names
 * ──────────────────────────
 *  ``<area>.<verb>`` — e.g. ``home.open`` ``cart.item_added``
 *  ``checkout.address_selected`` ``order.placed`` ``review.submit``.
 *  See the doc's "Data Flow" tables for the canonical set.
 */

const ENDPOINT = '/api/v1/analytics/events/'
const QUEUE_KEY = 'micha-track-queue-v1'
const SESSION_KEY = 'micha-track-session-v1'
const FLUSH_MS = 800
const MAX_BATCH = 8
const MAX_QUEUE = 200      // hard cap so a broken queue doesn't grow forever

// Hard-redact PII keys before sending — mirrors backend.
const REDACT = [
  /password/i, /passwd/i, /pwd/i, /secret/i, /token/i, /jwt/i,
  /card/i, /cvv/i, /cvc/i, /pin\b/i, /ssn/i, /bi\b/i, /nif/i,
  /authorization/i,
]

function scrub(obj) {
  if (!obj || typeof obj !== 'object') return {}
  const out = {}
  for (const [k, v] of Object.entries(obj)) {
    if (REDACT.some(re => re.test(k))) {
      out[k] = '[REDACTED]'
    } else if (v && typeof v === 'object' && !Array.isArray(v)) {
      out[k] = scrub(v)
    } else if (typeof v === 'string' && v.length > 1024) {
      out[k] = v.slice(0, 1024) + '…'
    } else {
      out[k] = v
    }
  }
  return out
}

function getSessionId() {
  try {
    let s = sessionStorage.getItem(SESSION_KEY)
    if (!s) {
      s = (crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`).slice(0, 64)
      sessionStorage.setItem(SESSION_KEY, s)
    }
    return s
  } catch { return '' }
}

function readQueue() {
  try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]') } catch { return [] }
}

function writeQueue(arr) {
  try {
    // Trim from the head if oversized.
    if (arr.length > MAX_QUEUE) arr.splice(0, arr.length - MAX_QUEUE)
    localStorage.setItem(QUEUE_KEY, JSON.stringify(arr))
  } catch {}
}

let buffer = []
let flushTimer = null

function flush(force = false) {
  if (!force && buffer.length < MAX_BATCH) {
    if (flushTimer) return
    flushTimer = setTimeout(() => { flushTimer = null; flush(true) }, FLUSH_MS)
    return
  }
  if (flushTimer) { clearTimeout(flushTimer); flushTimer = null }
  // Combine in-memory buffer with the durable queue so we drain
  // any offline backlog in the same request.
  const all = [...readQueue(), ...buffer]
  buffer = []
  if (!all.length) return
  // Clear the durable queue optimistically. If the request fails
  // we'll restore the leftovers.
  writeQueue([])
  // Use fetch with keepalive so an in-flight request survives a
  // page unload (e.g. navigation away from MICHA back to home).
  fetch(ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ events: all }),
    credentials: 'include',
    keepalive: true,
  }).catch(() => {
    // Restore the events for the next attempt.
    const merged = [...readQueue(), ...all]
    writeQueue(merged)
  })
}

// Flush on page unload / blur so events aren't lost.
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => flush(true), { capture: true })
  window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flush(true)
  })
  // Drain any leftover queue from previous session on boot.
  setTimeout(() => flush(true), 600)
}

export function track(event, properties = {}) {
  if (!event) return
  try {
    buffer.push({
      event: String(event).slice(0, 80),
      properties: scrub(properties || {}),
      session_id: getSessionId(),
      path: typeof location !== 'undefined' ? location.pathname : '',
      ts: new Date().toISOString(),
    })
    flush()
  } catch {}
}

/** Track the current route on every navigation. Mount-and-forget. */
export function useRouteTracker(path) {
  if (typeof window === 'undefined') return
  try {
    track('route.view', { path })
  } catch {}
}

export const userTrack = { track, useRouteTracker, getSessionId }
export default userTrack
