/**
 * Service Worker registration — Tier 7.
 *
 * Gated by VITE_ENABLE_SW (default 'true' in prod, 'false' in dev).
 * Wired from main.jsx on a slight delay so it never delays first paint.
 */

export function registerServiceWorker() {
  if (typeof window === 'undefined') return
  if (!('serviceWorker' in navigator)) return

  const enabled = import.meta.env?.VITE_ENABLE_SW
  const explicitlyEnabled = enabled === 'true' || enabled === true
  const explicitlyDisabled = enabled === 'false' || enabled === false

  // In dev mode (or whenever the operator explicitly turns the SW off
  // via VITE_ENABLE_SW=false) we must NOT just skip registration —
  // any SW installed during an earlier production session would
  // continue to intercept fetches and feed stale JS bundles to the
  // WebView. This is the source-of-truth way to recover the
  // "I edited LoginPage.jsx but the simulator still runs the old
  // code" footgun: actively unregister + flush caches.
  const shouldDisable = explicitlyDisabled ||
    (import.meta.env?.DEV && !explicitlyEnabled)
  if (shouldDisable) {
    Promise.resolve()
      .then(() => navigator.serviceWorker.getRegistrations())
      .then(regs => Promise.all(regs.map(r => r.unregister())))
      .then(() => {
        if ('caches' in window) {
          return caches.keys().then(keys =>
            Promise.all(keys.map(k => caches.delete(k))))
        }
      })
      .catch(() => {})
    return
  }

  // Register after first paint to keep TTI clean.
  const start = () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .catch(() => { /* silent — SW is opportunistic */ })
  }
  if (document.readyState === 'complete') start()
  else window.addEventListener('load', start, { once: true })
}
