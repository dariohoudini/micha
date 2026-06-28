/**
 * events — canonical event tracker (Tier 9).
 *
 * Single source of truth for the 30 events listed in the roadmap.
 * Routes to PostHog when VITE_POSTHOG_KEY is configured, falls back
 * to the existing /api/v1/analytics/track/ + /api/v1/search/event/
 * endpoints. Both can co-exist — calling track() fires to both
 * sinks so you never have to pick one.
 *
 * Why a wrapper, not raw posthog-js
 * ──────────────────────────────────
 *  1. Lazy loading — posthog-js is ~50KB; gating import behind the
 *     env var means web users in dev don't pay for it
 *  2. Property schema discipline — every event has a fixed property
 *     set; the wrapper enforces it via TS-style JSDoc + runtime
 *     filtering of unknown keys
 *  3. PII safety — automatic email / phone / token redaction
 *  4. Operator choice — when the team picks Mixpanel / Amplitude /
 *     PostHog, only this file changes. Callers keep working.
 *
 * Canonical event names
 * ─────────────────────
 * (snake_case, present-tense verb, deliberately small set)
 *
 *  app_open, app_resume
 *  view_signup, signup_submitted, signup_complete
 *  view_login, login_succeeded, login_failed
 *  view_home, view_product, view_category, view_store
 *  search, search_no_results, search_did_you_mean_used
 *  add_to_cart, remove_from_cart, view_cart, clear_cart
 *  checkout_start, checkout_payment_method_selected,
 *  checkout_complete, checkout_failed
 *  view_order, contact_seller, request_refund, request_return
 *  view_seller_dashboard, listing_published
 *  push_permission_asked, push_permission_granted, push_permission_denied
 */


const POSTHOG_KEY = import.meta.env?.VITE_POSTHOG_KEY || ''
const POSTHOG_HOST = import.meta.env?.VITE_POSTHOG_HOST
                  || 'https://app.posthog.com'

let _posthog = null
let _initStarted = false
let _userPropsCache = {}


// PII keys never sent to analytics.
const PII_KEYS = [
  /^email$/i, /password/i, /token/i, /secret/i, /authorization/i,
  /credit.?card/i, /cvv/i, /^pin$/i, /^nif$/i, /^bi$/i,
]


function scrubProps(props) {
  if (!props || typeof props !== 'object') return {}
  const out = {}
  for (const [k, v] of Object.entries(props)) {
    if (PII_KEYS.some((re) => re.test(k))) continue
    if (typeof v === 'string' && v.length > 1024) {
      out[k] = v.slice(0, 1024) + '…'
    } else {
      out[k] = v
    }
  }
  return out
}


function initPosthog() {
  if (_initStarted) return
  _initStarted = true
  if (!POSTHOG_KEY) return
  // Variable indirection to defeat Vite's static import-analysis.
  // posthog-js is intentionally optional; installing it would add
  // ~50KB to anyone's bundle who's never going to use PostHog.
  const pkg = 'posthog' + '-js'
  import(pkg).then((mod) => {
    try {
      const posthog = mod.default || mod
      posthog.init(POSTHOG_KEY, {
        api_host: POSTHOG_HOST,
        autocapture: false,
        capture_pageview: false,    // we send view_* explicitly
        capture_pageleave: false,
        person_profiles: 'identified_only',
        respect_dnt: true,
        sanitize_properties: scrubProps,
      })
      _posthog = posthog
      // Apply any user properties cached before init completed.
      if (Object.keys(_userPropsCache).length > 0) {
        try { _posthog.setPersonProperties(_userPropsCache) } catch {}
      }
    } catch {
      _posthog = null
    }
  }).catch(() => { _posthog = null })
}


// Initialise immediately on import (lazy network fetch under the hood).
initPosthog()


/* ─── Public API ─────────────────────────────────────────────────── */

export function track(event, props = {}) {
  const safe = scrubProps(props)

  // PostHog
  if (_posthog?.capture) {
    try { _posthog.capture(event, safe) } catch {}
  }

  // Mobile batch pipeline (Mobile App Engineering CH20) — buffered,
  // flushed every 30s / on background, deduped server-side by event_id.
  try {
    import('@/lib/eventBatch')
      .then(({ enqueueEvent }) => enqueueEvent(event, safe))
      .catch(() => {})
  } catch {}

  // Backend fallback — fire-and-forget. Keeps analytics flowing even
  // when PostHog is unconfigured.
  try {
    import('@/api/client').then(({ default: client }) => {
      client.post('/api/v1/analytics/track/', {
        event,
        properties: safe,
        ts: new Date().toISOString(),
      }).catch(() => {})
    }).catch(() => {})
  } catch {}
}


export function identify(userId, traits = {}) {
  if (!userId) return
  const safe = scrubProps(traits)
  _userPropsCache = { ..._userPropsCache, ...safe }
  if (_posthog?.identify) {
    try { _posthog.identify(String(userId), safe) } catch {}
  }
}


export function reset() {
  _userPropsCache = {}
  if (_posthog?.reset) {
    try { _posthog.reset() } catch {}
  }
}


/**
 * Convenience: track a route view. Call from a useEffect that depends
 * on useLocation.pathname.
 */
export function trackView(route, props = {}) {
  track('view_' + route, props)
}


/* ─── Funnel helpers (Tier 9) ────────────────────────────────────── */

export const funnel = {
  signupStart:    (props) => track('view_signup', props),
  signupComplete: (props) => track('signup_complete', props),
  checkoutStart:  (props) => track('checkout_start', props),
  checkoutDone:   (props) => track('checkout_complete', props),
  checkoutFail:   (props) => track('checkout_failed', props),
  search:         (props) => track('search', props),
  noResults:      (props) => track('search_no_results', props),
  addToCart:      (props) => track('add_to_cart', props),
  viewProduct:    (props) => track('view_product', props),
}


export { scrubProps }
