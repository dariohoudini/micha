/**
 * frontend/src/lib/sentry.js
 * ───────────────────────────
 *
 * Frontend error reporting (R1 Sprint 3).
 *
 * Why this exists
 * ───────────────
 * Pre-Sprint-3 the FE had ErrorBoundary catching React crashes but
 * NOTHING sent them anywhere. Server logs only saw 500s from the
 * backend; FE crashes (white screens, broken renders, unhandled
 * promise rejections) were invisible to ops.
 *
 * Design choices
 * ──────────────
 *  • Lazy-load @sentry/browser. The SDK is ~50KB gzipped — gating
 *    behind ``import()`` means if VITE_SENTRY_DSN is unset (dev /
 *    preview) we never ship the bytes.
 *  • PII scrub before send — never leak access tokens, emails, JWT
 *    bodies, or password fields to Sentry.
 *  • Source-map upload is OPERATOR work (Sentry CLI in CI). This
 *    module just initialises the client + provides report().
 *
 * Public API
 * ──────────
 *   initSentry()           call once from main.jsx (gated by env)
 *   reportError(err, ctx)  manual reporting from catch blocks
 */

const DSN = import.meta.env?.VITE_SENTRY_DSN || ''
const ENVIRONMENT = import.meta.env?.MODE || 'production'
const RELEASE = import.meta.env?.VITE_RELEASE || ''

let _sentryClient = null
let _initStarted = false


// PII scrub patterns. Aligned with backend PII redactor — same data,
// same scrubbing rules, regardless of which side caught the error.
const SENSITIVE_KEYS = [
  /pass(word|wd)?/i,
  /secret/i,
  /token/i,
  /auth/i,
  /bearer/i,
  /credit.?card/i,
  /cvv/i,
  /pin/i,
  /^(nif|bi)$/i,
]

function scrubKey(key) {
  if (typeof key !== 'string') return false
  return SENSITIVE_KEYS.some(re => re.test(key))
}

function scrubObject(obj, depth = 0) {
  if (depth > 4) return '[truncated]'
  if (obj === null || obj === undefined) return obj
  if (Array.isArray(obj)) return obj.map(v => scrubObject(v, depth + 1))
  if (typeof obj !== 'object') return obj
  const out = {}
  for (const [k, v] of Object.entries(obj)) {
    if (scrubKey(k)) {
      out[k] = '[REDACTED]'
    } else {
      out[k] = scrubObject(v, depth + 1)
    }
  }
  return out
}


function beforeSend(event) {
  try {
    if (event.request) {
      const req = event.request
      if (req.headers) {
        for (const h of ['Authorization', 'Cookie', 'X-Auth-Token']) {
          if (h in req.headers) req.headers[h] = '[REDACTED]'
        }
      }
      if (req.data) req.data = scrubObject(req.data)
    }
    if (event.user) {
      // Keep id for correlation, drop email/ip.
      event.user = { id: event.user.id || event.user.user_id }
    }
    if (event.extra) event.extra = scrubObject(event.extra)
  } catch {
    // Never let scrubbing crash the report.
  }
  return event
}


export function initSentry() {
  if (_initStarted) return
  _initStarted = true
  if (!DSN) {
    // No DSN configured → silent no-op. Common in dev.
    return
  }
  // Lazy import keeps the SDK out of the bundle when unused.
  import('@sentry/browser').then((Sentry) => {
    try {
      Sentry.init({
        dsn: DSN,
        environment: ENVIRONMENT,
        release: RELEASE || undefined,
        // Conservative sample rates — adjust per traffic.
        tracesSampleRate: 0.1,
        // Send PII-scrubbed events only.
        beforeSend,
        // Capture unhandled promise rejections + console.error.
        integrations: (defaults) => defaults,
      })
      _sentryClient = Sentry
    } catch {
      // Swallow init failures — Sentry must never crash the app.
    }
  }).catch(() => {
    // @sentry/browser not installed in this build — fine in dev.
  })
}


export function reportError(err, context) {
  if (!_sentryClient) {
    // Fallback: console.error so dev still sees it.
    // eslint-disable-next-line no-console
    console.error('[MICHA] reportError:', err, context)
    return
  }
  try {
    _sentryClient.withScope((scope) => {
      if (context && typeof context === 'object') {
        scope.setExtras(scrubObject(context))
      }
      _sentryClient.captureException(err)
    })
  } catch {
    // ignore
  }
}
