import axios from 'axios'
import { tokenStorage } from './tokenStorage'

// ── Base URL resolution ──────────────────────────────────────────
// Codebase convention: call sites already include /api/ in their path
// (e.g., client.post('/api/v1/auth/register/', ...)). So in DEV we
// want baseURL='' — axios then uses the page origin + path verbatim,
// and the Vite proxy on /api/ forwards to Django. Works from any
// host (laptop browser, iOS simulator, phone over LAN).
//
// Prod / Capacitor native: VITE_API_BASE_URL must be set to the
// absolute origin (no /api suffix) since paths already carry /api.
const DEFAULT_BASE = import.meta.env?.DEV
  ? ''
  : 'http://127.0.0.1:8000'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE,
  headers: { 'Content-Type': 'application/json' },
  timeout: 12000,
})

// Path patterns that REQUIRE an Idempotency-Key header on the server side
// (the backend has @idempotent(required=True) on these views).
//
// We auto-attach a generated key on the FIRST request and reuse it for
// any retry of the same axios config object (e.g., the 401-refresh
// retry path below sets ``original._retry = true`` and re-runs the
// same config). Manual "click again" by the user generates a new axios
// request → new key, which is the correct behaviour (intentional retry
// = fresh attempt).
const IDEMPOTENCY_REQUIRED_PATTERNS = [
  /\/orders\/checkout\/?$/,
  /\/orders\/[^/]+\/refund\/?$/,
  /\/orders\/[^/]+\/return\/?$/,
  /\/orders\/[^/]+\/cancel\/?$/,
  /\/wallet\/payout\/?$/,
  /\/products\/?$/,                       // create
  /\/products\/create\/?$/,               // create (path the app actually posts to —
                                          //  backend @idempotent(required=True) 400s without the key)
  /\/products\/[^/]+\/variants\/?$/,
  /\/inventory\/reserve\/?$/,
  /\/giftcards\/redeem\/?$/,
  /\/auth\/register\/?$/,
]

function pathRequiresIdempotency(url) {
  if (!url) return false
  return IDEMPOTENCY_REQUIRED_PATTERNS.some((re) => re.test(url))
}

function generateIdempotencyKey() {
  if (crypto?.randomUUID) return crypto.randomUUID()
  // Fallback for environments without crypto.randomUUID
  return `${Date.now()}-${Math.random().toString(36).slice(2, 12)}-${Math.random().toString(36).slice(2, 12)}`
}

// Mobile App Engineering CH12 — device fingerprint sent on every
// request (fraud correlation, ATO detection, deferred deep links).
// getFingerprint() is async; cache the value once resolved so the
// synchronous request interceptor can attach it. Requests fired
// before resolution simply omit the header — acceptable warm-up gap.
let _deviceFp = ''
import('./fingerprint')
  .then(({ getFingerprint }) => getFingerprint())
  .then((fp) => { _deviceFp = fp || '' })
  .catch(() => {})

// ── Request: attach access token + request ID + idempotency key ───────────
api.interceptors.request.use(
  (config) => {
    const token = tokenStorage.getAccessToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    // Correlate requests in server logs
    config.headers['X-Request-ID'] = crypto.randomUUID?.() || Math.random().toString(36).slice(2)
    config.headers['X-App-Version'] = import.meta.env.VITE_APP_VERSION || '1.0.0'
    if (_deviceFp) {
      config.headers['X-Device-Fingerprint'] = _deviceFp
    }

    // Idempotency-Key for money-mutating endpoints.
    //
    // Order of precedence:
    //   1. Caller passed an explicit key in config.headers — respect it.
    //      (Use case: a hook that wants the SAME key across multiple
    //      manual retries within a single checkout intent.)
    //   2. Path matches the required-idempotency set — auto-generate.
    //   3. Other paths — leave header unset.
    //
    // The auto-attached key survives axios's internal retries (401 →
    // refresh → retry the same config) because the same config object
    // is re-used. Manual user retries create a new request → new key,
    // which is intended.
    const method = (config.method || 'get').toLowerCase()
    if (['post', 'patch', 'put', 'delete'].includes(method)
        && !config.headers['Idempotency-Key']
        && pathRequiresIdempotency(config.url)) {
      config.headers['Idempotency-Key'] = generateIdempotencyKey()
    }

    // Strip any accidentally included sensitive fields
    if (config.data) {
      const { password, ...rest } = config.data
      // Keep password for auth endpoints only
      if (config.url?.includes('/auth/')) {
        config.data = { ...rest, ...(password !== undefined ? { password } : {}) }
      }
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ── Response: auto-refresh on 401 ─────────────────────────────────────────
let isRefreshing = false
let failedQueue = []

const processQueue = (error, token = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error)
    else resolve(token)
  })
  failedQueue = []
}

// User Process Flow §20.8 — auto-log every mutation + every error
// to the UserEvent table. Read-only GETs are skipped because they
// would bury the signal in volume. The analytics endpoint itself is
// excluded to break what would otherwise be an infinite loop.
// Telemetry endpoints are excluded from the API KPI counters — the
// flush requests would otherwise measure themselves forever.
const TELEMETRY_PATH = /\/mobile\/(perf|events|crashes|sync)\//

api.interceptors.response.use(
  (response) => {
    // Mobile App Engineering CH24 — API success-rate KPI counter
    try {
      if (!TELEMETRY_PATH.test(response.config?.url || '')) {
        import('@/lib/perfMetrics')
          .then(({ recordApiSuccess }) => recordApiSuccess()).catch(() => {})
      }
    } catch {}
    try {
      const method = (response.config?.method || 'get').toLowerCase()
      const url = response.config?.url || ''
      if (['post', 'patch', 'put', 'delete'].includes(method) && !url.includes('/analytics/events')) {
        import('@/lib/userTrack').then(({ track }) => {
          track('api.request', {
            method: method.toUpperCase(),
            path: url,
            status: response.status,
          })
        }).catch(() => {})
      }
    } catch {}
    return response
  },
  async (error) => {
    try {
      const cfg = error.config || {}
      const url = cfg.url || ''
      if (!url.includes('/analytics/events')) {
        import('@/lib/userTrack').then(({ track }) => {
          track('api.error', {
            method: (cfg.method || 'get').toUpperCase(),
            path: url,
            status: error.response?.status || 0,
            error: (error.response?.data?.error || error.response?.data?.detail || error.message || '').toString().slice(0, 200),
          })
        }).catch(() => {})
      }
    } catch {}
    const original = error.config

    // Mobile App Engineering CH23 — single retry on pure network
    // errors (no HTTP response: dropped connection, DNS, timeout).
    // 4xx/5xx are NOT retried here. Idempotency keys are preserved
    // because the same config object is re-run.
    if (!error.response && original && !original._netRetry) {
      original._netRetry = true
      await new Promise((resolve) => setTimeout(resolve, 1000))
      return api(original)
    }

    // CH24 — API failure KPI counter (final failures only: network
    // errors that already burned the retry, and non-401 HTTP errors;
    // 401s usually recover via the refresh path below).
    if ((!error.response || error.response.status !== 401)
        && !TELEMETRY_PATH.test(original?.url || '')) {
      try {
        import('@/lib/perfMetrics')
          .then(({ recordApiFailure }) => recordApiFailure()).catch(() => {})
      } catch {}
    }

    if (error.response?.status === 401 && !original._retry) {
      if (isRefreshing) {
        // Queue requests while refresh is in progress
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then(token => {
          original.headers.Authorization = `Bearer ${token}`
          return api(original)
        })
      }

      original._retry = true
      isRefreshing = true

      const refreshToken = tokenStorage.getRefreshToken()

      if (!refreshToken) {
        tokenStorage.clearAll()
        window.location.href = '/login'
        return Promise.reject(error)
      }

      try {
        const { data } = await axios.post(
          `${import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'}/api/v1/auth/token/refresh/`,
          { refresh: refreshToken }
        )
        tokenStorage.setAccessToken(data.access)
        processQueue(null, data.access)
        original.headers.Authorization = `Bearer ${data.access}`
        return api(original)
      } catch (refreshError) {
        processQueue(refreshError, null)
        tokenStorage.clearAll()
        window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

export default api
