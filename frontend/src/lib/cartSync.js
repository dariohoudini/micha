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
import { toast } from '@/components/ui/Toast'
import { useAuthStore } from '@/stores/authStore'
import { useCartStore } from '@/stores/cartStore'

const DEBOUNCE_MS = 500

// Guest-First doc CH12: surface every merge conflict so the user sees
// what changed before checkout — never a silent drop / cap / re-price.
function surfaceConflicts(conflicts) {
  if (!Array.isArray(conflicts) || conflicts.length === 0) return
  const removed = conflicts.filter(c => c.kind === 'removed')
  const capped = conflicts.filter(c => c.kind === 'stock_capped')
  const priced = conflicts.filter(c => c.kind === 'price_changed')
  if (removed.length) {
    toast.error(removed.length === 1
      ? `"${removed[0].title || 'Um artigo'}" já não está disponível.`
      : `${removed.length} artigos do carrinho já não estão disponíveis.`)
  }
  if (capped.length) {
    toast.success(capped.length === 1
      ? `Quantidade de "${capped[0].title || 'um artigo'}" ajustada ao stock.`
      : `${capped.length} artigos ajustados ao stock disponível.`)
  }
  if (priced.length) {
    toast.success(priced.length === 1
      ? `O preço de "${priced[0].title || 'um artigo'}" foi actualizado.`
      : `${priced.length} preços foram actualizados.`)
  }
}

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
    // Anonymous cart — mirror it to the SERVER-SIDE guest cart
    // (Guest-First doc CH6) so it survives reinstalls, reaches other
    // devices, and merges into the account at signup even if
    // localStorage is gone. Local remains the source of truth for the
    // anon UX; the server is the durable copy.
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      setSyncStatus('offline')
      return
    }
    try {
      const { getDeviceId } = await import('@/lib/guestProfile')
      const { items: localItems, replaceItems } = useCartStore.getState()
      if (localItems.length > 0) {
        await client.put('/api/v1/guest/cart/', {
          device_id: getDeviceId(),
          items: localItems.filter(i => i && i.id).map(i => ({
            product_id: i.id,
            quantity: Math.max(1, Math.min(100, Number(i.quantity) || 1)),
            variant_combo_id: i.variantComboId || i.variant_combo_id || null,
            price_at_add: i.price,
            title: i.title || '',
          })),
        })
      } else {
        // Empty local cart (fresh install / cleared storage): recover
        // the durable guest cart from the server, if any.
        const res = await client.get('/api/v1/guest/cart/', {
          params: { device_id: getDeviceId() },
        })
        const serverItems = res?.data?.items || []
        if (serverItems.length > 0) replaceItems(serverItems)
      }
      setSyncStatus('idle')
    } catch {
      setSyncStatus('idle')   // guest mirroring is best-effort, never noisy
    }
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
    // A stable per-snapshot Idempotency-Key: a lost response on a flaky
    // network retries the SAME merge without doubling quantities (the
    // decorator replays the cached result). The key is derived from the
    // item set so distinct cart states get distinct keys.
    const snapshotKey = 'cart-merge-' + items
      .map(i => `${i.product_id}:${i.variant_combo_id || ''}:${i.quantity}`)
      .sort().join('|').slice(0, 200)
    const res = await client.post('/api/v1/cart/merge/', { items },
      { headers: { 'Idempotency-Key': snapshotKey } })
    const cart = res?.data?.cart || {}
    const serverItems = cart.items || []
    replaceItems(serverItems)
    surfaceConflicts(res?.data?.conflicts)
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
