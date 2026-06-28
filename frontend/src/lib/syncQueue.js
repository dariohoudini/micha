/**
 * syncQueue — generic offline mutation queue (Mobile App Engineering CH4).
 *
 * cartSync.js already handles the cart (server-authoritative merge).
 * This queue covers the OTHER offline-queueable mutations from the doc:
 * wishlist add/remove and review submit. Actions performed while
 * offline are persisted to localStorage and replayed in order when
 * connectivity returns (online event / app foreground / manual flush).
 *
 * Doc-mandated semantics:
 *   • idempotency_key generated AT QUEUE TIME — replays after a network
 *     failure reuse the same key, so the server never applies twice
 *   • give up after 3 retries → notify + drop (notifyFailure)
 *   • conflict strategy: server wins. WISHLIST_ADD is idempotent,
 *     WISHLIST_REMOVE already-gone is a no-op success.
 *   • every replay outcome is reported to /api/v1/mobile/sync/replay/
 *     so "every touch is logged" and the offline-sync KPI has data.
 */
const QUEUE_KEY = 'micha_sync_queue_v1'
const MAX_RETRIES = 3

let _queue = []
let _flushing = false
let _listeners = []   // (event, payload) => void — for toast wiring

function load() {
  try {
    const raw = localStorage.getItem(QUEUE_KEY)
    if (raw) _queue = JSON.parse(raw)
  } catch { _queue = [] }
}

function persist() {
  try { localStorage.setItem(QUEUE_KEY, JSON.stringify(_queue)) } catch {}
}

export function onSyncEvent(fn) {
  _listeners.push(fn)
  return () => { _listeners = _listeners.filter(l => l !== fn) }
}

function emit(event, payload) {
  _listeners.forEach(fn => { try { fn(event, payload) } catch {} })
}

/**
 * Queue an action. type: 'WISHLIST_ADD' | 'WISHLIST_REMOVE' |
 * 'REVIEW_SUBMIT'. Returns the queued item (with its idempotency key).
 */
export function enqueue(type, payload) {
  const item = {
    id: crypto.randomUUID(),   // doubles as the Idempotency-Key
    type,
    payload,
    createdAt: Date.now(),
    retryCount: 0,
  }
  _queue.push(item)
  persist()
  // If we're actually online, replay immediately (optimistic UI has
  // already updated — this makes the server catch up right away).
  if (navigator.onLine) flush()
  return item
}

export function pendingCount() { return _queue.length }

async function executeAction(client, action) {
  const headers = { 'Idempotency-Key': action.id }
  switch (action.type) {
    case 'WISHLIST_ADD':
      return client.post('/api/v1/wishlist/',
        { product: action.payload.productId }, { headers })
    case 'WISHLIST_REMOVE':
      return client.delete(
        `/api/v1/wishlist/${action.payload.wishlistItemId}/`, { headers })
    case 'REVIEW_SUBMIT':
      return client.post('/api/v1/reviews/', action.payload, { headers })
    default:
      throw new Error(`unknown sync action: ${action.type}`)
  }
}

const ACTION_TYPE_MAP = {
  WISHLIST_ADD: 'wishlist_add',
  WISHLIST_REMOVE: 'wishlist_remove',
  REVIEW_SUBMIT: 'review_submit',
}

async function reportReplay(client, action, status, conflictReason = '') {
  try {
    await client.post('/api/v1/mobile/sync/replay/', {
      action_type: ACTION_TYPE_MAP[action.type] || 'other',
      idempotency_key: action.id,
      status,
      retry_count: action.retryCount,
      conflict_reason: conflictReason,
      payload: action.payload,
    })
  } catch {}  // KPI logging must never block the queue
}

/** Replay everything pending. Safe to call repeatedly. */
export async function flush() {
  if (_flushing || _queue.length === 0 || !navigator.onLine) return
  _flushing = true
  try {
    const { default: client } = await import('@/api/client')
    const pending = [..._queue]
    for (const action of pending) {
      try {
        await executeAction(client, action)
        _queue = _queue.filter(a => a.id !== action.id)
        persist()
        reportReplay(client, action, 'applied')
      } catch (error) {
        const status = error.response?.status
        if (status === 409 || status === 404 || status === 400) {
          // Server wins — item out of stock / already removed / invalid.
          _queue = _queue.filter(a => a.id !== action.id)
          persist()
          reportReplay(client, action, 'conflict',
            error.response?.data?.error || `http_${status}`)
          emit('conflict', { action, status })
        } else {
          action.retryCount++
          if (action.retryCount >= MAX_RETRIES) {
            _queue = _queue.filter(a => a.id !== action.id)
            persist()
            reportReplay(client, action, 'failed', 'max_retries')
            emit('failed', { action })
          } else {
            persist()
          }
        }
      }
    }
  } finally {
    _flushing = false
  }
}

/** Wire connectivity + foreground listeners. Call once from main.jsx. */
export function initSyncQueue() {
  load()
  window.addEventListener('online', () => { flush() })
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') flush()
  })
  if (navigator.onLine) flush()
}
