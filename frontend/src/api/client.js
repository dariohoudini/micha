import axios from 'axios'
import { tokenStorage } from './tokenStorage'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api',
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

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config

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
