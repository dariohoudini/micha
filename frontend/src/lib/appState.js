/**
 * appState — foreground/background lifecycle manager
 * (Mobile App Engineering CH14, plus the killed-state recovery flow).
 *
 * On BACKGROUND:
 *   • stamp lastBackgroundTime (drives the stale-data rule below)
 *   • flush the analytics buffer via sendBeacon (eventBatch handles it)
 *
 * On FOREGROUND:
 *   • background > 5 min → invalidate critical react-query caches
 *     (cart, orders, notifications) so prices/stock are never stale
 *   • flush the offline sync queue + cart sync
 *
 * KILLED-STATE RECOVERY (doc CH14): checkout marks itself in
 * localStorage via markCheckoutInProgress(). On next launch,
 * checkIncompleteCheckout() asks the server whether the order actually
 * went through — navigate to confirmation if placed, back to cart if not.
 *
 * Uses visibilitychange — fires in both the browser and the Capacitor
 * webview; the Capacitor App plugin pause/resume events map to the
 * same hidden/visible states.
 */
const STALE_AFTER_MS = 5 * 60 * 1000
const CHECKOUT_KEY = 'micha_checkout_in_progress'

let _lastBackgroundTime = 0
let _started = false

async function onForeground() {
  const backgroundDuration = _lastBackgroundTime
    ? Date.now() - _lastBackgroundTime : 0

  if (backgroundDuration > STALE_AFTER_MS) {
    try {
      const { queryClient } = await import('@/lib/queryClient')
      queryClient.invalidateQueries({ queryKey: ['cart'] })
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    } catch {}
  }

  try {
    const { flush } = await import('@/lib/syncQueue')
    flush()
  } catch {}
  try {
    const { triggerCartSync } = await import('@/lib/cartSync')
    triggerCartSync?.()
  } catch {}
}

function onBackground() {
  _lastBackgroundTime = Date.now()
  // eventBatch installs its own visibilitychange beacon flush;
  // nothing else needs to run synchronously here.
}

/** Call once from main.jsx. */
export function initAppState() {
  if (_started) return
  _started = true
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') onBackground()
    else onForeground()
  })
}

/* ── Killed-state checkout recovery ────────────────────────────────── */

export function markCheckoutInProgress(orderId) {
  try { localStorage.setItem(CHECKOUT_KEY, String(orderId)) } catch {}
}

export function clearCheckoutInProgress() {
  try { localStorage.removeItem(CHECKOUT_KEY) } catch {}
}

/**
 * Call on app launch. Returns:
 *   {recovered: false}                          — nothing pending
 *   {recovered: true, placed: true,  orderId}   — go to confirmation
 *   {recovered: true, placed: false, orderId}   — resume from cart
 */
export async function checkIncompleteCheckout() {
  let orderId = null
  try { orderId = localStorage.getItem(CHECKOUT_KEY) } catch {}
  if (!orderId) return { recovered: false }
  clearCheckoutInProgress()
  try {
    const { default: client } = await import('@/api/client')
    const { data } = await client.get(`/api/v1/orders/${orderId}/`)
    const placed = ['placed', 'paid', 'processing', 'shipped',
      'completed'].includes(data.status)
    return { recovered: true, placed, orderId }
  } catch {
    return { recovered: true, placed: false, orderId }
  }
}
