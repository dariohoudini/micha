/**
 * crashReport — self-hosted crash ingest (Mobile App Engineering CH19).
 *
 * Complements lib/sentry.js: Sentry handles deep diagnostics when a
 * DSN is configured; THIS module always reports to our own backend
 * (POST /api/v1/mobile/crashes/) where crashes are grouped by stack
 * hash, counted per user, and watched by the 5×-baseline spike alert
 * (apps/mobile_app). Works with zero external dependencies — critical
 * for Angola deployments where a Sentry subscription may not exist.
 *
 * Wired from:
 *   • ErrorBoundary.componentDidCatch  (render crashes)
 *   • window 'error' + 'unhandledrejection' (everything else)
 *
 * PII safety: only the error type/message/stack leave the device —
 * never form values or storage contents.
 */
const MAX_REPORTS_PER_SESSION = 20   // a crash loop must not DDoS us
let _reported = 0
let _installed = false

export async function reportCrash(error, context = {}) {
  if (_reported >= MAX_REPORTS_PER_SESSION) return
  _reported++
  try {
    const body = {
      error_type: (error?.name || 'Error').slice(0, 120),
      error_message: String(error?.message || error || '').slice(0, 300),
      stack_trace: String(error?.stack || '').slice(0, 20000),
      platform: window.Capacitor?.getPlatform?.() || 'web',
      app_version: import.meta.env?.VITE_APP_VERSION || 'dev',
      os_version: '',
      device_model: navigator.userAgent.slice(0, 64),
      context,
    }
    const { default: client } = await import('@/api/client')
    await client.post('/api/v1/mobile/crashes/', body)
  } catch {}  // the crash reporter must never crash
}

/** Global handlers — call once from main.jsx. */
export function installCrashHandlers() {
  if (_installed) return
  _installed = true
  window.addEventListener('error', (event) => {
    if (event.error) reportCrash(event.error, { source: 'window.onerror' })
  })
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason instanceof Error
      ? event.reason : new Error(String(event.reason))
    reportCrash(reason, { source: 'unhandledrejection' })
  })
}
