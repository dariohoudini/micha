/**
 * frontend/src/lib/cartSync.js
 * ─────────────────────────────
 *
 * Offline-aware cart synchroniser.
 *
 * Why this exists
 * ───────────────
 * Angola's mobile networks drop frequently. Pre-R5-B the cart store
 * persisted items to localStorage but had no link back to the server
 * cart — a user who lost connectivity mid-session, added items, then
 * came back online would never push those items up. Worse: the next
 * device they logged in on saw an empty server cart. Lost sales.
 *
 * What it does
 * ─────────────
 * Listens to:
 *   • browser ``online`` event
 *   • ``visibilitychange`` (tab/app coming to foreground)
 *   • a manual ``triggerCartSync()`` export for post-login wiring
 *
 * On each trigger, if the user is authenticated AND there are local
 * items AND ``navigator.onLine`` is true, it POSTs the local cart to
 * ``/api/v1/cart/merge/``. That endpoint is idempotent (apps/cart/
 * views.py:MergeAnonCartView) — repeated calls with the same payload
 * produce the same end state, bounded by available stock. After a
 * successful response the engine calls ``replaceItems()`` to adopt
 * the server's authoritative shape.
 *
 * Failure handling
 * ─────────────────
 * Network failure → syncStatus='error', schedule retry on next event.
 * Auth failure (401) → caller's interceptor refreshes the token;
 *   we leave the items in place and the next event will retry.
 * 4xx other → log + leave items. We do NOT delete local items on a
 *   bad request: that would lose the cart silently. Better the user
 *   sees a stale cart than no cart.
 *
 * Throttling
 * ──────────
 * Multiple events (online + focus + manual trigger) can fire in rapid
 * succession. The engine collapses them via a 500ms debounce + an
 * in-flight flag so concurrent triggers wait for the prior call.
 */
import client from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useCartStore } from '@/stores/cartStore'

const DEBOUNCE_MS = 500

let inflight = false
let debounceTimer = null
let listenersAttached = false


function localItemsForMerge() {
  // Map the local store shape to the /merge/ payload shape. The local
  // store may have items added pre-R5-B with different field names —
  // be defensive about variant combos.
  const { items } = useCartStore.getState()
  return items
    .filter(i => i && i.id)
    .map(i => {
      const out = {
        product_id: i.id,
        quantity: Math.max(1, Math.min(100, Number(i.quantity) || 1)),
      }
      const combo = i.variantComboId || i.variant_combo_id || null
      if (combo) out.variant_combo_id = combo
      return out
    })
}


async function performSync() {
  const { isAuth } = useAuthStore.getState()
  const { setSyncStatus, replaceItems } = useCartStore.getState()

  if (!isAuth) {
    // Anonymous cart — nothing to sync to the server. Status reflects
    // local-only mode; this is normal pre-login state.
    setSyncStatus('idle')
    return
  }
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    setSyncStatus('offline')
    return
  }

  const items = localItemsForMerge()
  if (items.length === 0) {
    // Empty local cart — still GET the server cart to populate the UI
    // with any items the user added on another device. Cheap and
    // important for cross-device continuity.
    setSyncStatus('syncing')
    try {
      const res = await client.get('/api/v1/cart/')
      const serverItems = res?.data?.items || []
      replaceItems(serverItems)
      setSyncStatus('synced')
    } catch (e) {
      setSyncStatus('error', e?.message || 'cart fetch failed')
    }
    return
  }

  setSyncStatus('syncing')
  try {
    const res = await client.post('/api/v1/cart/merge/', { items })
    const cart = res?.data?.cart || {}
    const serverItems = cart.items || []
    replaceItems(serverItems)
    setSyncStatus('synced')
  } catch (e) {
    // 401 is handled by the axios refresh interceptor — if we land
    // here on 401, refresh already failed; treat as error and retry
    // on next event. 4xx other than 401 means the payload is bad and
    // retrying won't help, but we still leave items in place.
    const status = e?.response?.status
    const msg = `merge failed status=${status || 'network'}`
    setSyncStatus('error', msg)
  }
}


function scheduleSync() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(async () => {
    debounceTimer = null
    if (inflight) {
      // Another sync already running; reschedule once it finishes.
      // Simplest correct policy: wait one more debounce window.
      scheduleSync()
      return
    }
    inflight = true
    try {
      await performSync()
    } finally {
      inflight = false
    }
  }, DEBOUNCE_MS)
}


/**
 * Public: manually trigger a sync. Call this immediately after a
 * successful login so the user's pre-login local cart gets folded
 * into their server cart on day one.
 */
export function triggerCartSync() {
  scheduleSync()
}


/**
 * Public: attach window event listeners + initial sync attempt.
 * Idempotent — calling twice is safe (the listeners-attached flag
 * prevents double-binding).
 *
 * Returns a cleanup function for React useEffect.
 */
export function attachCartSync() {
  if (listenersAttached) {
    // Re-trigger a sync (e.g., user just logged in) without
    // re-binding listeners.
    scheduleSync()
    return () => {}
  }
  if (typeof window === 'undefined') return () => {}

  const onOnline = () => scheduleSync()
  const onVisibility = () => {
    if (document.visibilityState === 'visible') scheduleSync()
  }

  window.addEventListener('online', onOnline)
  document.addEventListener('visibilitychange', onVisibility)
  listenersAttached = true

  // First-load sync.
  scheduleSync()

  return () => {
    window.removeEventListener('online', onOnline)
    document.removeEventListener('visibilitychange', onVisibility)
    listenersAttached = false
  }
}
