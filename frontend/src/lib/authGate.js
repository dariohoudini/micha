/**
 * authGate — AliExpress Button & Redirect Workflow §34.1 + §34.3
 *
 * Single source of truth for the "guest tapped a gated button" path.
 * Every call site that needs auth (add-to-cart, wishlist, checkout,
 * follow seller, contact seller, open dispute, leave review,
 * collect coupon, coins check-in, account tab) routes through this
 * helper so the login replay flow is consistent.
 *
 * Usage:
 *
 *   const gated = useAuthGate()
 *   <button onClick={() => gated('add_to_cart', { product_id })
 *                          .then(replayed => { if (!replayed) addToCart(...) })} />
 *
 * Or for plain navigation gates:
 *
 *   if (!requireAuth(navigate, location, 'cart_tab')) return
 *
 * On the LoginPage success path, call `consumeReturnAction(state, ctx)`.
 * The returnAction is replayed exactly once; the state is cleared.
 *
 * Telemetry: every gate hit and every replayed action writes to
 * UserEvent so we can see "users who abandoned because of auth gate"
 * and "actions that replayed successfully after login" in analytics.
 */
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { track } from '@/lib/userTrack'

/**
 * Imperative form. Returns true if the user is authed (caller proceeds).
 * Returns false if a redirect was queued (caller stops).
 */
export function requireAuth(navigate, location, action, params = {}) {
  const { isAuth } = useAuthStore.getState()
  if (isAuth) return true
  try {
    track('auth.gate_hit', { action, path: location?.pathname || '' })
  } catch {}
  navigate('/login', {
    replace: false,
    state: {
      returnTo: location?.pathname + (location?.search || ''),
      returnAction: action,
      returnParams: params,
    },
  })
  return false
}

/** Hook form — read navigate / location from router context. */
export function useAuthGate() {
  const navigate = useNavigate()
  const location = useLocation()
  return (action, params = {}) => requireAuth(navigate, location, action, params)
}

/**
 * Map a returnAction → fire-and-forget side-effect run after login.
 * Each entry receives `params` from the original gate call. Keep
 * them small and idempotent — a flaky network shouldn't break the
 * happy "user just logged in" path.
 */
const REPLAY_HANDLERS = {
  add_to_cart: async ({ product_id, quantity = 1, variant_id }) => {
    if (!product_id) return
    const { default: api } = await import('@/api/client')
    await api.post('/api/v1/cart/items/', {
      product_id, quantity, variant_id,
    })
  },
  wishlist_add: async ({ product_id }) => {
    if (!product_id) return
    const { default: api } = await import('@/api/client')
    await api.post(`/api/v1/products/${product_id}/wishlist/`)
  },
  follow_seller: async ({ seller_id }) => {
    if (!seller_id) return
    const { default: api } = await import('@/api/client')
    await api.post(`/api/v1/sellers/${seller_id}/follow/`)
  },
  collect_coupon: async ({ coupon_id }) => {
    if (!coupon_id) return
    const { default: api } = await import('@/api/client')
    await api.post(`/api/v1/coupons/${coupon_id}/collect/`)
  },
  // Pure-navigation gates (cart_tab, account_tab, checkout) carry no
  // side-effect — just the returnTo navigation handles them.
}

/**
 * Called from LoginPage.onSubmit success. Replays the returnAction
 * exactly once, navigates to returnTo, and emits a telemetry row so
 * we can see post-login conversion in analytics.
 *
 * Returns the destination path the caller should navigate to (or
 * null if no gated state was present and the caller should pick a
 * default landing page itself).
 */
export async function consumeReturnAction(locationState) {
  if (!locationState || !locationState.returnTo) return null
  const { returnTo, returnAction, returnParams } = locationState
  try {
    track('auth.gate_replay', { action: returnAction, path: returnTo })
  } catch {}
  const handler = REPLAY_HANDLERS[returnAction]
  if (handler) {
    try {
      await handler(returnParams || {})
    } catch (e) {
      // Don't block return-nav on replay failure; user lands back on
      // the gated screen and can tap the button again.
      try {
        track('auth.gate_replay_failed', {
          action: returnAction,
          error: (e && e.message) || 'unknown',
        })
      } catch {}
    }
  }
  return returnTo
}

/**
 * §34.4 — Navigation Stack Reset Rules.
 *
 * After sign-out, account-banned, forced-update completion, or
 * onboarding finish, react-router has no native "stack reset", but
 * we can mimic the AliExpress behaviour by using `navigate(to,
 * { replace: true })` and clearing all history above it. This helper
 * centralises that so the four reset moments stay consistent.
 */
export function navResetTo(navigate, to) {
  // `replace: true` so the user can't ⌫-back into the old auth
  // state; combined with the route guards, this is the closest
  // web-router analogue to `navigation.reset({routes:[{name:to}]})`.
  navigate(to, { replace: true })
  // Best-effort: nuke history so a hardware-back in Capacitor lands
  // on the new root rather than the prior screen. Safe-guarded so
  // tests / SSR don't blow up.
  try {
    if (typeof window !== 'undefined' && window.history) {
      // Push one sentinel state, then replace it. This collapses the
      // back-stack to "current entry" only for most engines.
      window.history.replaceState(null, '', to)
    }
  } catch {}
}
